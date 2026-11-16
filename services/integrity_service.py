import json
import os
from pathlib import Path
from typing import Any

from infrastructure.audit import verify_audit, verify_checkpoint, write_checkpoint
from infrastructure.hash_engine import sha256_file
from services.case_service import CaseService
from services.evidence_service import EvidenceService
from infrastructure.tsk_adapter import TSKAdapter
from domain.models import Evidence, FileSystemInfo, Partition


class IntegrityService:
    def __init__(self, cases: CaseService):
        self.cases = cases

    def audit_status(self) -> dict[str, Any]:
        audit_path = self.cases.root / "audit.jsonl"
        checkpoint_path = self.cases.root / "audit_checkpoint.json"
        return {
            "chain": verify_audit(audit_path),
            "checkpoint": verify_checkpoint(audit_path, checkpoint_path),
            "audit_path": str(audit_path),
            "checkpoint_path": str(checkpoint_path),
        }

    def create_checkpoint(self) -> dict[str, Any]:
        audit_path = self.cases.root / "audit.jsonl"
        checkpoint_path = self.cases.root / "audit_checkpoint.json"
        return write_checkpoint(audit_path, checkpoint_path)

    def verify_evidence(self) -> int:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before verifying evidence")
        verifier = EvidenceService(
            self.cases,
            TSKAdapter(Path(os.environ.get("RELIC_TSK_BIN", r"D:\sleuthkit\sleuthkit\bin"))),
        )
        verified = 0
        for evidence_id in case.evidence_ids:
            path = self.cases.case_path(case.case_id) / "evidence" / f"{evidence_id}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            evidence = Evidence(
                data["evidence_id"], data["name"], data["source_path"], data["size_bytes"],
                data["loaded_at"], data.get("image_type", "raw"), data.get("sha256"),
                data.get("hash_status", "pending"),
                [Partition(**item) for item in data.get("partitions", [])],
                [FileSystemInfo(**item) for item in data.get("filesystems", [])],
            )
            if verifier.verify_end_hash(evidence):
                verified += 1
        return verified

    def evidence_status(self) -> list[dict[str, Any]]:
        case = self.cases.active_case
        if case is None:
            return []
        statuses = []
        for evidence_id in case.evidence_ids:
            path = self.cases.case_path(case.case_id) / "evidence" / f"{evidence_id}.json"
            if not path.exists():
                statuses.append({"evidence_id": evidence_id, "status": "incomplete"})
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            statuses.append({
                "evidence_id": evidence_id,
                "status": data.get("hash_status", "incomplete"),
                "initial_sha256": data.get("sha256"),
                "end_sha256": data.get("end_sha256"),
                "hash_match": data.get("hash_match"),
                "partitions": bool(data.get("partitions")),
                "filesystems": bool(data.get("filesystems")),
            })
        return statuses

    def quality_checks(self) -> list[dict[str, Any]]:
        case = self.cases.active_case
        if case is None:
            return [{"name": "案件信息", "status": "incomplete", "details": "没有打开案件"}]
        evidence = self.evidence_status()
        audit = self.audit_status()
        checks = [
            {"name": "案件信息", "status": "pass" if case.case_number and case.name and case.examiner else "warning",
             "details": "案件核心字段已填写"},
            {"name": "证据加载", "status": "pass" if evidence else "incomplete",
             "details": f"{len(evidence)} 个证据"},
            {"name": "初始哈希", "status": "pass" if evidence and all(item.get("initial_sha256") for item in evidence) else "incomplete",
             "details": "所有证据均有基线哈希" if evidence else "没有证据"},
            {"name": "分区识别", "status": "pass" if evidence and all(item["partitions"] for item in evidence) else "warning",
             "details": "分区信息已保存"},
            {"name": "文件系统信息", "status": "pass" if evidence and all(item["filesystems"] for item in evidence) else "warning",
             "details": "文件系统信息已保存"},
            {"name": "结束复核", "status": "pass" if evidence and all(item.get("hash_match") is True for item in evidence) else "incomplete",
             "details": "结束哈希与基线一致" if evidence else "未完成"},
            {"name": "分析任务", "status": self._task_status(case.case_id)[0],
             "details": self._task_status(case.case_id)[1]},
            {"name": "审计链", "status": "pass" if audit["chain"]["valid"] else "warning",
             "details": "; ".join(audit["chain"]["errors"]) or "哈希链有效"},
            {"name": "检查点", "status": "pass" if audit["checkpoint"]["valid"] else "warning",
             "details": audit["checkpoint"]["status"]},
            {"name": "导出记录", "status": "pass" if (self.cases.case_path(case.case_id) / "exports.jsonl").exists() else "warning",
             "details": "存在导出记录" if (self.cases.case_path(case.case_id) / "exports.jsonl").exists() else "尚无导出"},
        ]
        return checks

    def _task_status(self, case_id: str) -> tuple[str, str]:
        path = self.cases.case_path(case_id) / "task_history.jsonl"
        if not path.exists():
            return "warning", "没有任务历史"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if not records:
            return "warning", "没有任务历史"
        latest = records[-1]
        if latest.get("status") == "completed":
            return "pass", "最近任务已完成"
        if latest.get("status") in {"failed", "cancelled"}:
            return "warning", f"最近任务状态：{latest['status']}"
        return "incomplete", f"最近任务状态：{latest.get('status')}"

    def summary(self) -> list[dict[str, str]]:
        evidence = self.evidence_status()
        exports = []
        case = self.cases.active_case
        if case is not None:
            path = self.cases.case_path(case.case_id) / "exports.jsonl"
            if path.exists():
                exports = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        return [
            {
                "item": f"证据 {item['evidence_id']} 初始 SHA-256",
                "value": item.get("initial_sha256") or "未完成",
                "status": "pass" if item.get("initial_sha256") else "incomplete",
            }
            for item in evidence
        ] + [
            {
                "item": f"证据 {item['evidence_id']} 结束复核",
                "value": item.get("end_sha256") or "未完成",
                "status": "pass" if item.get("hash_match") is True else "incomplete",
            }
            for item in evidence
        ] + [
            {
                "item": f"导出 {item.get('inode', '')} SHA-256",
                "value": item.get("sha256", ""),
                "status": "pass",
            }
            for item in exports
        ]

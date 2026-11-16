import json
import platform
import sys
from collections import Counter
from pathlib import Path

from infrastructure.audit import utc_now, verify_audit
from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService
from services.integrity_service import IntegrityService
from services.timeline_service import TimelineService


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _value(value, missing="未提供"):
    return missing if value is None or value == "" else str(value)


class ReportService:
    def __init__(
        self,
        cases: CaseService,
        integrity: IntegrityService,
        timeline: TimelineService,
        tsk_version: str = "未验证",
    ):
        self.cases = cases
        self.integrity = integrity
        self.timeline = timeline
        self.tsk_version = tsk_version

    def generate(self) -> Path:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before generating a report")
        output = self.cases.case_path(case.case_id) / "reports" / f"forensic_report_{utc_now().replace(':', '').replace('-', '')}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._render(case, generated_at=utc_now()), encoding="utf-8")
        self.cases.audit.append(
            "local-user", "report.generated", "case", case.case_id,
            {"format": "markdown", "path": str(output)},
            {"status": "success", "path": str(output)},
        )
        output.write_text(self._render(case, generated_at=utc_now()), encoding="utf-8")
        return output

    def preview(self, report_path: Path) -> str:
        if report_path.suffix.casefold() != ".md":
            raise ValueError("only Markdown reports can be previewed")
        return report_path.read_text(encoding="utf-8")

    def _render(self, case, generated_at: str) -> str:
        root = self.cases.case_path(case.case_id)
        evidence = self._evidence(root, case.evidence_ids)
        files = _read_jsonl(root / "files.jsonl")
        analysis = _read_jsonl(root / "analysis_results.jsonl")
        annotations = _read_jsonl(root / "annotations.jsonl")
        exports = _read_jsonl(root / "exports.jsonl")
        tasks = _read_jsonl(root / "task_history.jsonl")
        audit_path = self.cases.root / "audit.jsonl"
        audit_records = _read_jsonl(audit_path)
        audit_status = verify_audit(audit_path)
        checkpoint = self.integrity.audit_status()["checkpoint"]
        quality = self.integrity.quality_checks()
        timeline = self.timeline.events()
        type_values = [
            item.get("detected_type", "UNKNOWN")
            for item in files
            if item.get("detected_type")
        ]
        type_values.extend(
            item.get("detected_type", "UNKNOWN")
            for item in self._analysis_data(analysis, "file_type")
        )
        type_counts = Counter(type_values)
        anomalies = [
            item for item in self._analysis_data(analysis, "file_type")
            if item.get("extension_mismatch") is True
        ]
        searches = self._analysis_data(analysis, "keyword_search")
        image_results = self._analysis_data(analysis, "image_metadata")
        passed_quality = sum(item["status"] == "pass" for item in quality)
        incomplete_quality = sum(item["status"] == "incomplete" for item in quality)
        type_lines = [
            f"- {kind}：{count}" for kind, count in sorted(type_counts.items())
        ] or ["- 类型统计：未提供"]
        conclusion = (
            "通过：当前数据中的证据哈希、审计链和质量检查均支持完整性结论。"
            if audit_status["valid"] and evidence and all(item.get("hash_match") is True for item in evidence)
            and incomplete_quality == 0
            else "未完成或存在警告：报告未将缺失复核、缺失数据或审计异常解释为成功。"
        )
        lines = [
            "# Relic 数字取证报告",
            "",
            f"- 生成时间（UTC）：{generated_at}",
            "- 报告格式：Markdown",
            "- 只生成 Markdown，不生成 HTML。",
            "",
            "## 1. 案件信息",
            f"- 案件 ID：{case.case_id}",
            f"- 案件编号：{_value(case.case_number)}",
            f"- 案件名称：{_value(case.name)}",
            f"- 取证对象：{_value(case.subject)}",
            f"- 案件描述：{_value(case.description)}",
            f"- 案件状态：{_value(case.status)}",
            "",
            "## 2. 取证人员",
            f"- 取证人员：{_value(case.examiner)}",
            "- 确认签名：____________________________",
            "- 确认日期：____________________________",
            "",
            "## 3. 实验环境",
            f"- 操作系统：{platform.platform()}",
            f"- Python：{sys.version.split()[0]}",
            f"- TSK CLI：{_value(self.tsk_version)}",
            "- 时区：UTC",
            "",
            "## 4. 证据镜像信息",
        ]
        if evidence:
            for item in evidence:
                lines += [
                    f"### {item['evidence_id']}",
                    f"- 名称：{_value(item.get('name'))}",
                    f"- 原始路径：{_value(item.get('source_path'))}",
                    f"- 大小：{item.get('size_bytes', '未提供')} bytes",
                    f"- 加载时间（UTC）：{_value(item.get('loaded_at'))}",
                    f"- 镜像类型：{_value(item.get('image_type'))}",
                    f"- SHA-256 基准值：{_value(item.get('sha256'), '未完成')}",
                    f"- 结束复核 SHA-256：{_value(item.get('end_sha256'), '未完成')}",
                    f"- 哈希一致：{_status_value(item.get('hash_match'))}",
                    "",
                    "分区：",
                ]
                partitions = item.get("partitions", [])
                lines += [
                    f"- {p.get('index')}: {p.get('description')}，start={p.get('start_sector')}，length={p.get('length_sectors')} sectors"
                    for p in partitions
                ] or ["- 未完成"]
                lines.append("文件系统：")
                lines += [
                    f"- {fs.get('filesystem_type')}，offset={fs.get('offset_sectors')} sectors，status={fs.get('status')}"
                    for fs in item.get("filesystems", [])
                ] or ["- 未完成"]
        else:
            lines.append("- 未完成：案件没有已保存证据。")
        lines += [
            "",
            "## 5. 文件数量和类型统计",
            f"- 文件清单记录数：{len(files) if files else '未完成'}",
            *type_lines,
            "",
            "## 6. 扩展名异常检测摘要",
            f"- 异常数量：{len(anomalies) if analysis else '未完成'}",
            *[f"- {item.get('source_path')}: 检测为 {item.get('detected_type')}，扩展名 {item.get('extension')}" for item in anomalies],
            "- 说明：扩展名异常不等同于恶意行为。",
            "",
            "## 7. 关键词搜索摘要",
        ]
        if searches:
            for item in searches:
                lines.append(f"- 关键词：{item.get('keyword', '未提供')}；命中：{item.get('match_count', 0)}")
        else:
            lines.append("- 未完成：没有关键词搜索结果。")
        lines += ["", "## 8. 图片元数据分析摘要"]
        if image_results:
            for item in image_results:
                lines.append(f"- {item.get('source_path')}：{json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append("- 未完成：没有图片元数据结果。")
        lines += [
            "",
            "## 9. 时间线摘要",
            f"- 事件数量：{len(timeline) if timeline else '未完成'}",
            *[f"- {event.timestamp} UTC | {event.source_kind} | {event.event_type} | {event.summary}" for event in timeline[:100]],
            "",
            "## 10. 文件标记和备注摘要",
        ]
        lines += [f"- {item.get('entry_id')}：{item.get('label')}；{_value(item.get('note'), '无备注')}" for item in annotations] or ["- 未提供"]
        lines += ["", "## 11. 文件导出清单及哈希"]
        lines += [f"- inode {item.get('inode')}：{item.get('destination_path')}；SHA-256={_value(item.get('sha256'))}" for item in exports] or ["- 未提供"]
        lines += [
            "",
            "## 12. 审计日志摘要",
            f"- 记录数：{len(audit_records)}",
            f"- 最近序号：{audit_status['last_sequence']}",
            f"- 最近记录哈希：{audit_status['last_hash']}",
            f"- 最近动作：{audit_records[-1].get('action') if audit_records else '未提供'}",
            "",
            "## 13. 哈希链验证结果",
            f"- 状态：{'通过' if audit_status['valid'] else '异常'}",
            f"- 错误：{'; '.join(audit_status['errors']) or '无'}",
            f"- 检查点：{checkpoint.get('status', 'missing')}",
            "- 信任边界：哈希链可发现部分修改，但不能阻止有文件系统权限者重写整个日志。",
            "",
            "## 14. 自动化质量检查结果",
            f"- 通过：{passed_quality}；未完成：{incomplete_quality}；警告：{len(quality) - passed_quality - incomplete_quality}",
        ]
        lines += [f"- {item['name']}：{item['status']}；{item['details']}" for item in quality]
        lines += [
            "",
            "## 15. 完整性结论",
            f"- {conclusion}",
            "- 软件级只读不等同于硬件写保护器。",
            "",
            "## 16. 取证人员确认栏",
            "- 本报告由案件持有人在核对原始证据、哈希和审计状态后确认。",
            "- 签名：____________________________",
            "- 日期（UTC）：______________________",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _analysis_data(records: list[dict], analysis_type: str) -> list[dict]:
        data = []
        for record in records:
            if record.get("analysis_type") == analysis_type:
                item = dict(record.get("data") or {})
                item["source_path"] = record.get("source_path")
                data.append(item)
        return data

    @staticmethod
    def _evidence(root: Path, evidence_ids: list[str]) -> list[dict]:
        result = []
        for evidence_id in evidence_ids:
            path = root / "evidence" / f"{evidence_id}.json"
            if path.exists():
                result.append(json.loads(path.read_text(encoding="utf-8")))
        return result


def _status_value(value) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "未完成"

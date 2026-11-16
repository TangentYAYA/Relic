import json
import shutil
from pathlib import Path

from infrastructure.audit import (
    GENESIS_HASH, AuditWriter, verify_audit, verify_checkpoint, write_checkpoint,
)
from services.case_service import CaseService
from services.integrity_service import IntegrityService


def test_audit_chain_genesis_and_verification(tmp_path):
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(path)
    first = writer.append("tester", "case.created", "case", "c1", {}, {"status": "success"})
    second = writer.append("tester", "case.opened", "case", "c1", {}, {"status": "success"})
    assert first["previous_hash"] == GENESIS_HASH
    assert second["previous_hash"] == first["record_hash"]
    result = verify_audit(path)
    assert result["valid"] is True
    assert result["last_sequence"] == 2
    assert result["last_hash"] == second["record_hash"]


def test_tamper_copy_detects_content_order_and_sequence(tmp_path):
    source = tmp_path / "audit.jsonl"
    writer = AuditWriter(source)
    writer.append("tester", "one", "test", "1", {}, {})
    writer.append("tester", "two", "test", "2", {}, {})
    copy = tmp_path / "audit-copy.jsonl"
    shutil.copyfile(source, copy)
    records = [json.loads(line) for line in copy.read_text().splitlines()]
    records[0]["action"] = "tampered"
    records[1]["sequence"] = 4
    copy.write_text("\n".join(json.dumps(item) for item in records) + "\n")
    result = verify_audit(copy)
    assert result["valid"] is False
    assert any("record_hash mismatch" in error for error in result["errors"])
    assert any("expected sequence" in error for error in result["errors"])


def test_checkpoint_detects_tail_change(tmp_path):
    audit = tmp_path / "audit.jsonl"
    checkpoint = tmp_path / "audit_checkpoint.json"
    writer = AuditWriter(audit)
    writer.append("tester", "one", "test", "1", {}, {})
    saved = write_checkpoint(audit, checkpoint)
    assert saved["last_sequence"] == 1
    assert verify_checkpoint(audit, checkpoint)["valid"] is True
    writer.append("tester", "two", "test", "2", {}, {})
    result = verify_checkpoint(audit, checkpoint)
    assert result["valid"] is False
    assert "checkpoint sequence does not match audit" in result["errors"]


def test_quality_checks_report_incomplete_without_evidence(tmp_path):
    cases = CaseService(tmp_path / "cases")
    cases.create_case("INT-1", "Integrity", "Tester", "fixture", "quality")
    service = IntegrityService(cases)
    checks = {item["name"]: item for item in service.quality_checks()}
    assert checks["案件信息"]["status"] == "pass"
    assert checks["证据加载"]["status"] == "incomplete"
    assert checks["初始哈希"]["status"] == "incomplete"

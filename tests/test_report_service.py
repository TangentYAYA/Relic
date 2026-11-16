import hashlib
import json
from pathlib import Path

from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService
from services.integrity_service import IntegrityService
from services.report_service import ReportService
from services.timeline_service import TimelineService


def test_report_contains_real_case_fields_and_hashes(tmp_path):
    root = tmp_path / "cases"
    cases = CaseService(root)
    case = cases.create_case("REPORT-001", "Report fixture", "Examiner A", "Laptop", "known fixture")
    evidence_id = "evidence-1"
    image = tmp_path / "disk.dd"
    image.write_bytes(b"known evidence")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (root / case.case_id / "evidence" / f"{evidence_id}.json").write_text(json.dumps({
        "evidence_id": evidence_id, "name": image.name, "source_path": str(image),
        "size_bytes": image.stat().st_size, "loaded_at": "2024-01-01T00:00:00Z",
        "image_type": "raw", "sha256": digest, "end_sha256": digest,
        "hash_status": "verified", "hash_match": True,
        "partitions": [{"index": 1, "description": "TEST", "start_sector": 0,
                        "length_sectors": 10, "end_sector": 9}],
        "filesystems": [{"filesystem_id": "fs-0", "filesystem_type": "TESTFS",
                         "offset_sectors": 0, "raw_output": "real output",
                         "status": "identified"}],
    }), encoding="utf-8")
    case.evidence_ids.append(evidence_id)
    cases.update_case(case)
    case_root = root / case.case_id
    JsonlWriter(case_root / "files.jsonl").append({
        "entry_id": "file-1", "path": "/notes.txt", "inode": 3,
        "size_bytes": 4, "detected_type": "TEXT",
        "modified_at": "2024-01-02T00:00:00Z",
    })
    JsonlWriter(case_root / "analysis_results.jsonl").append({
        "result_id": "result-1", "analysis_type": "file_type",
        "status": "succeeded", "source_path": "/wrong.jpg",
        "created_at": "2024-01-02T00:00:00Z",
        "data": {"detected_type": "JPEG", "extension": ".txt", "extension_mismatch": True},
    })
    JsonlWriter(case_root / "analysis_results.jsonl").append({
        "result_id": "result-2", "analysis_type": "keyword_search",
        "status": "succeeded", "source_path": "<multiple>",
        "created_at": "2024-01-02T00:00:00Z",
        "data": {"keyword": "needle", "match_count": 1},
    })
    JsonlWriter(case_root / "annotations.jsonl").append({
        "entry_id": "file-1", "label": "important", "note": "reviewed",
    })
    export_hash = hashlib.sha256(b"exported").hexdigest()
    JsonlWriter(case_root / "exports.jsonl").append({
        "inode": 3, "destination_path": str(case_root / "exports" / "3_notes.txt"),
        "sha256": export_hash,
    })

    service = ReportService(cases, IntegrityService(cases), TimelineService(cases), "TSK test 4.14.0")
    report = service.generate()
    content = report.read_text(encoding="utf-8")
    for required in [
        "# Relic 数字取证报告", "REPORT-001", "Examiner A", "TSK test 4.14.0",
        digest, "TESTFS", "文件数量和类型统计", "JPEG", "关键词搜索摘要",
        "图片元数据分析摘要", "时间线摘要", "important", export_hash,
        "哈希链验证结果", "自动化质量检查结果", "完整性结论",
        "report.generated", "只生成 Markdown",
    ]:
        assert required in content
    assert report.suffix == ".md"
    assert report.parent.name == "reports"
    assert service.preview(report) == content
    assert "<html" not in content.lower()
    assert "report.generated" in (root / "audit.jsonl").read_text(encoding="utf-8")

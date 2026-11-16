import hashlib
import struct
from pathlib import Path

import pytest

from domain.models import Evidence
from infrastructure.hash_engine import sha256_file
from infrastructure.tsk_adapter import TSKAdapter, TSKProcessError
from services.case_service import CaseService
from services.evidence_service import EvidenceService


TSK_BIN = Path(r"D:\sleuthkit\sleuthkit\bin")


def make_mbr_image(path: Path) -> None:
    data = bytearray(4 * 1024 * 1024)
    data[446 + 4] = 0x07
    data[446 + 8:446 + 12] = struct.pack("<I", 1)
    data[446 + 12:446 + 16] = struct.pack("<I", 8191)
    data[510:512] = b"\x55\xaa"
    path.write_bytes(data)


def test_create_reopen_and_isolate_cases(tmp_path):
    root = tmp_path / "cases"
    first_service = CaseService(root)
    first = first_service.create_case("CASE-001", "First", "Alice", "Device A", "one")
    second = first_service.create_case("CASE-002", "Second", "Bob", "Device B", "two")

    reopened = CaseService(root)
    cases = reopened.list_cases()
    assert {case.case_id for case in cases} == {first.case_id, second.case_id}
    assert (root / first.case_id / "case.json").exists()
    assert (root / second.case_id / "case.json").exists()
    assert first.case_id != second.case_id


def test_case_metadata_update_persists(tmp_path):
    service = CaseService(tmp_path / "cases")
    case = service.create_case("CASE-001", "Before", "Alice", "Device", "old")
    case.name = "After"
    case.description = "new"
    service.update_case(case)
    reopened = CaseService(tmp_path / "cases").open_case(case.case_id)
    assert reopened.name == "After"
    assert reopened.description == "new"


def test_missing_image_is_rejected(tmp_path):
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-001", "Case", "Examiner", "Subject", "Description")
    service = EvidenceService(cases, TSKAdapter(TSK_BIN))
    with pytest.raises(FileNotFoundError):
        service.load_raw(tmp_path / "missing.dd")


def test_raw_load_and_real_mmls_partition_identification(tmp_path):
    image = tmp_path / "sample.dd"
    make_mbr_image(image)
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-001", "Case", "Examiner", "Subject", "Description")
    service = EvidenceService(cases, TSKAdapter(TSK_BIN))

    evidence = service.load_raw(image)
    partition = next(item for item in evidence.partitions if item.description.startswith("NTFS"))
    assert evidence.source_path == str(image.resolve())
    assert evidence.size_bytes == image.stat().st_size
    assert partition.start_sector == 1
    assert partition.length_sectors == 8191
    assert (tmp_path / "cases" / cases.active_case.case_id / "evidence").is_dir()


def test_fsstat_failure_is_explicit_for_invalid_filesystem(tmp_path):
    image = tmp_path / "sample.dd"
    make_mbr_image(image)
    adapter = TSKAdapter(TSK_BIN)
    with pytest.raises(TSKProcessError, match="fsstat failed"):
        adapter.inspect_filesystem(image, 1)


def test_sha256_streaming_correctness(tmp_path):
    image = tmp_path / "hash.bin"
    image.write_bytes((b"Relic evidence\n" * 10000) + b"end")
    updates = []
    digest, size = sha256_file(image, updates.append, chunk_size=4096)
    assert digest == hashlib.sha256(image.read_bytes()).hexdigest()
    assert size == image.stat().st_size
    assert updates[-1] == 100


def test_baseline_hash_is_persisted_and_audited(tmp_path):
    image = tmp_path / "sample.dd"
    image.write_bytes(b"evidence" * 1024)
    cases = CaseService(tmp_path / "cases")
    case = cases.create_case("CASE-001", "Case", "Examiner", "Subject", "Description")
    evidence_service = EvidenceService(cases, TSKAdapter(TSK_BIN))
    evidence = Evidence(
        evidence_id="e1",
        name=image.name,
        source_path=str(image),
        size_bytes=image.stat().st_size,
        loaded_at="now",
    )
    digest = evidence_service.calculate_baseline(evidence)
    assert digest == hashlib.sha256(image.read_bytes()).hexdigest()
    persisted = next((tmp_path / "cases" / case.case_id / "evidence").glob("e1.json")).read_text()
    assert digest in persisted
    audit = (tmp_path / "cases" / "audit.jsonl").read_text()
    assert "evidence.hash_baseline" in audit


def test_end_hash_verification_persists_match(tmp_path):
    image = tmp_path / "sample.dd"
    image.write_bytes(b"stable evidence")
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-001", "Case", "Examiner", "Subject", "Description")
    service = EvidenceService(cases, TSKAdapter(TSK_BIN))
    evidence = Evidence("e1", image.name, str(image), image.stat().st_size, "now")
    service.calculate_baseline(evidence)
    assert service.verify_end_hash(evidence) is True
    persisted = next((tmp_path / "cases" / cases.active_case.case_id / "evidence").glob("e1.json")).read_text()
    assert '"hash_status": "verified"' in persisted

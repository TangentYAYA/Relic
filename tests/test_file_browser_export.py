import hashlib
import struct
from pathlib import Path

import pytest

from infrastructure.tsk_adapter import TSKAdapter, TSKProcessError
from services.case_service import CaseService
from services.evidence_service import EvidenceService
from services.file_service import FileService


TSK_BIN = Path(r"D:\sleuthkit\sleuthkit\bin")


def make_fat_image(path: Path) -> bytes:
    content = b"known Relic content"
    child_content = b"child"
    data = bytearray(100 * 512)
    data[0:3] = b"\xeb\x3c\x90"
    data[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", data, 11, 512)
    data[13] = 1
    struct.pack_into("<H", data, 14, 1)
    data[16] = 2
    struct.pack_into("<H", data, 17, 32)
    struct.pack_into("<H", data, 19, 100)
    data[21] = 0xF8
    struct.pack_into("<H", data, 22, 1)
    data[510:512] = b"\x55\xaa"
    for offset in (512, 1024):
        struct.pack_into("<H", data, offset, 0xFFF8)
        struct.pack_into("<H", data, offset + 2, 0xFFFF)
        struct.pack_into("<H", data, offset + 4, 0xFFFF)
        struct.pack_into("<H", data, offset + 6, 0xFFFF)
        struct.pack_into("<H", data, offset + 8, 0xFFFF)
    root = 3 * 512
    data[root:root + 11] = b"TEST    TXT"
    data[root + 11] = 0x20
    struct.pack_into("<H", data, root + 26, 2)
    struct.pack_into("<I", data, root + 28, len(content))
    data[root + 32:root + 43] = b"SUBDIR     "
    data[root + 32 + 11] = 0x10
    struct.pack_into("<H", data, root + 32 + 26, 3)
    data[5 * 512:5 * 512 + len(content)] = content
    child = 6 * 512
    data[child:child + 11] = b"CHILD   TXT"
    data[child + 11] = 0x20
    struct.pack_into("<H", data, child + 26, 4)
    struct.pack_into("<I", data, child + 28, len(child_content))
    data[7 * 512:7 * 512 + len(child_content)] = child_content
    path.write_bytes(data)
    return content


def test_fls_istat_icat_export_round_trip(tmp_path):
    image = tmp_path / "known.img"
    content = make_fat_image(image)
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-FS", "Filesystem", "Tester", "fixture", "known content")
    evidence_service = EvidenceService(cases, TSKAdapter(TSK_BIN))
    evidence = evidence_service.load_raw(image)
    file_service = FileService(cases, TSKAdapter(TSK_BIN))

    listing, listing_count = file_service.write_listing(evidence, 0)
    entries = file_service.list_files(evidence, 0)
    test_file = next(entry for entry in entries if entry.name == "TEST.TXT")
    assert len(entries) >= 1
    assert listing_count == len(entries)
    assert len(listing.read_text(encoding="utf-8").splitlines()) == listing_count
    assert test_file.inode == 3
    assert test_file.size_bytes == len(content)
    assert test_file.entry_type == "file"

    stat = file_service.stat(evidence, 0, test_file.inode)
    assert "Directory Entry" in stat
    record = file_service.export_file(evidence, 0, test_file.inode, test_file.name)
    exported = Path(record.destination_path)
    assert exported.read_bytes() == content
    assert record.sha256 == hashlib.sha256(content).hexdigest()
    assert record.size_bytes == len(content)
    assert record.destination_path.startswith(str(tmp_path / "cases"))
    assert "file.exported" in (tmp_path / "cases" / "audit.jsonl").read_text()
    assert record.sha256 in (tmp_path / "cases" / cases.active_case.case_id / "exports.jsonl").read_text()


def test_file_listing_filters_without_reloading_source(tmp_path):
    image = tmp_path / "known.img"
    make_fat_image(image)
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-FS", "Filesystem", "Tester", "fixture", "filters")
    evidence = EvidenceService(cases, TSKAdapter(TSK_BIN)).load_raw(image)
    entries = FileService(cases, TSKAdapter(TSK_BIN)).list_files(evidence, 0)
    assert [entry.name for entry in entries if entry.name.endswith(".TXT")]
    assert not [entry for entry in entries if entry.name.endswith(".BIN")]


def test_directory_listing_uses_directory_inode(tmp_path):
    image = tmp_path / "known.img"
    make_fat_image(image)
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-FS", "Filesystem", "Tester", "fixture", "directory")
    evidence = EvidenceService(cases, TSKAdapter(TSK_BIN)).load_raw(image)
    service = FileService(cases, TSKAdapter(TSK_BIN))
    root_entries = service.list_files(evidence, 0)
    directory = next(entry for entry in root_entries if entry.name == "SUBDIR")
    children = service.list_files(evidence, 0, inode=directory.inode)
    assert [(entry.name, entry.size_bytes) for entry in children] == [("CHILD.TXT", 5)]


def test_export_invalid_inode_reports_error(tmp_path):
    image = tmp_path / "known.img"
    make_fat_image(image)
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-FS", "Filesystem", "Tester", "fixture", "error")
    evidence = EvidenceService(cases, TSKAdapter(TSK_BIN)).load_raw(image)
    service = FileService(cases, TSKAdapter(TSK_BIN))
    with pytest.raises(TSKProcessError, match="icat failed"):
        service.export_file(evidence, 0, 999999, "missing.bin")
    exports = tmp_path / "cases" / cases.active_case.case_id / "exports"
    assert not exports.exists() or not list(exports.iterdir())

import hashlib
import json
import uuid
from pathlib import Path

from domain.models import Evidence, ExportRecord, FileEntry
from infrastructure.audit import utc_now
from infrastructure.hash_engine import sha256_file
from infrastructure.repositories import JsonlWriter
from infrastructure.tsk_adapter import TSKAdapter
from services.case_service import CaseService


class FileService:
    def __init__(self, cases: CaseService, tsk: TSKAdapter):
        self.cases = cases
        self.tsk = tsk

    def list_files(
        self, evidence: Evidence, offset_sectors: int, recursive: bool = False, inode: int | None = None
    ) -> list[FileEntry]:
        return self.tsk.list_files(Path(evidence.source_path), offset_sectors, recursive, inode)

    def write_listing(
        self, evidence: Evidence, offset_sectors: int, recursive: bool = False,
        inode: int | None = None,
    ) -> tuple[Path, int]:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before writing a file listing")
        listing = self.cases.case_path(case.case_id) / "files.jsonl"
        writer = JsonlWriter(listing)
        count = 0
        for entry in self.tsk.iter_files(Path(evidence.source_path), offset_sectors, recursive, inode):
            writer.append(entry.__dict__)
            count += 1
        return listing, count

    def stat(self, evidence: Evidence, offset_sectors: int, inode: int) -> str:
        return self.tsk.stat(Path(evidence.source_path), offset_sectors, inode)

    def export_file(
        self, evidence: Evidence, offset_sectors: int, inode: int, name: str
    ) -> ExportRecord:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before exporting evidence")
        destination_dir = self.cases.case_path(case.case_id) / "exports"
        destination_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(name).name or f"inode-{inode}"
        destination = destination_dir / f"{inode}_{safe_name}"
        self.tsk.extract(Path(evidence.source_path), offset_sectors, inode, destination)
        digest, size = sha256_file(destination)
        record = ExportRecord(
            export_id=str(uuid.uuid4()),
            evidence_id=evidence.evidence_id,
            inode=inode,
            source_path=f"{evidence.source_path}:{inode}",
            destination_path=str(destination),
            size_bytes=size,
            sha256=digest,
            exported_at=utc_now(),
        )
        JsonlWriter(self.cases.case_path(case.case_id) / "exports.jsonl").append(record.__dict__)
        self.cases.audit.append(
            "local-user", "file.exported", "evidence", evidence.evidence_id,
            {"inode": inode, "destination": str(destination)}, {"status": "success", "sha256": digest},
        )
        return record

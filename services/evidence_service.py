import uuid
from pathlib import Path

from domain.models import Evidence
from infrastructure.audit import AuditWriter, utc_now
from infrastructure.hash_engine import sha256_file
from infrastructure.repositories import JsonRepository
from infrastructure.tsk_adapter import TSKAdapter
from infrastructure.tsk_adapter import TSKProcessError
from services.case_service import CaseService


class EvidenceService:
    def __init__(self, cases: CaseService, tsk: TSKAdapter):
        self.cases = cases
        self.tsk = tsk
        self.loaded_evidence: list[Evidence] = []

    def load_raw(self, image: Path) -> Evidence:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before loading evidence")
        image = image.resolve()
        if not image.is_file():
            raise FileNotFoundError(str(image))
        evidence = Evidence(str(uuid.uuid4()), image.name, str(image), image.stat().st_size, utc_now())
        try:
            evidence.partitions = self.tsk.inspect_partitions(image)
        except TSKProcessError as exc:
            try:
                evidence.filesystems.append(self.tsk.inspect_filesystem(image, 0))
            except TSKProcessError:
                raise exc
        directory = self.cases.case_path(case.case_id) / "evidence"
        JsonRepository(directory / f"{evidence.evidence_id}.json").write(evidence_to_dict(evidence))
        case.evidence_ids.append(evidence.evidence_id)
        self.cases.update_case(case)
        self.cases.audit.append("local-user", "evidence.loaded", "evidence", evidence.evidence_id, {"name": evidence.name}, {"status": "success"})
        self.loaded_evidence.append(evidence)
        return evidence

    def inspect_filesystem(self, evidence: Evidence, partition_index: int):
        partition = next(item for item in evidence.partitions if item.index == partition_index)
        info = self.tsk.inspect_filesystem(Path(evidence.source_path), partition.start_sector)
        evidence.filesystems.append(info)
        self._save(evidence)
        self.cases.audit.append("local-user", "evidence.filesystem_identified", "evidence", evidence.evidence_id, {"offset_sectors": partition.start_sector}, {"status": "success"})
        return info

    def calculate_baseline(self, evidence: Evidence, progress=None) -> str:
        digest, _ = sha256_file(Path(evidence.source_path), progress)
        evidence.sha256 = digest
        evidence.hash_status = "baseline"
        self._save(evidence)
        self.cases.audit.append("local-user", "evidence.hash_baseline", "evidence", evidence.evidence_id, {"algorithm": "SHA-256"}, {"status": "success", "sha256": digest})
        return digest

    def verify_end_hash(self, evidence: Evidence, progress=None) -> bool:
        digest, _ = sha256_file(Path(evidence.source_path), progress)
        evidence.end_sha256 = digest
        evidence.hash_match = bool(evidence.sha256 and evidence.sha256 == digest)
        evidence.hash_status = "verified" if evidence.hash_match else "mismatch"
        self._save(evidence)
        self.cases.audit.append(
            "local-user", "evidence.hash_end_verification", "evidence", evidence.evidence_id,
            {"algorithm": "SHA-256"}, {"status": evidence.hash_status, "sha256": digest},
        )
        return evidence.hash_match

    def _save(self, evidence: Evidence) -> None:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before saving evidence")
        JsonRepository(self.cases.case_path(case.case_id) / "evidence" / f"{evidence.evidence_id}.json").write(evidence_to_dict(evidence))


def evidence_to_dict(evidence: Evidence) -> dict:
    data = evidence.__dict__.copy()
    data["partitions"] = [item.__dict__ for item in evidence.partitions]
    data["filesystems"] = [item.__dict__ for item in evidence.filesystems]
    return data

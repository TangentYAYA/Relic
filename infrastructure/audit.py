import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .repositories import JsonlWriter

GENESIS_HASH = "0" * 64
AUDIT_FIELDS = (
    "schema_version", "sequence", "timestamp", "actor", "action", "object",
    "parameters_summary", "result", "error", "previous_hash",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuditWriter:
    def __init__(self, path: Path):
        self.writer = JsonlWriter(path)
        self.path = path
        self._lock = Lock()

    def append(
        self,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        parameters_summary: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.path.exists() and self.path.stat().st_size:
                verification = verify_audit(self.path)
                if not verification["valid"]:
                    raise RuntimeError(
                        "audit log is invalid; refusing to append: "
                        + "; ".join(verification["errors"][:3])
                    )
            previous_hash = GENESIS_HASH
            sequence = 1
            if self.path.exists():
                lines = self.path.read_text(encoding="utf-8").splitlines()
                if lines:
                    previous = json.loads(lines[-1])
                    sequence = int(previous["sequence"]) + 1
                    previous_hash = previous["record_hash"]
            record = {
                "schema_version": 1,
                "sequence": sequence,
                "timestamp": utc_now(),
                "actor": actor,
                "action": action,
                "object": {"type": object_type, "id": object_id},
                "parameters_summary": parameters_summary,
                "result": result,
                "error": error,
                "previous_hash": previous_hash,
            }
            record["record_hash"] = record_hash(record)
            self.writer.append(record)
            return record


def canonical_record(record: dict[str, Any]) -> bytes:
    payload = {field: record[field] for field in AUDIT_FIELDS}
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False
    ).encode("utf-8")


def record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_record(record)).hexdigest()


def verify_audit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "valid": True, "record_count": 0, "last_sequence": 0,
            "last_hash": GENESIS_HASH, "errors": [],
        }
    errors: list[str] = []
    previous_hash = GENESIS_HASH
    expected_sequence = 1
    last_hash = GENESIS_HASH
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
                continue
            missing = [field for field in (*AUDIT_FIELDS, "record_hash") if field not in record]
            if missing:
                errors.append(f"line {line_number}: missing fields {missing}")
                continue
            if record["sequence"] != expected_sequence:
                errors.append(
                    f"line {line_number}: expected sequence {expected_sequence}, "
                    f"got {record['sequence']}"
                )
            if record["previous_hash"] != previous_hash:
                errors.append(f"line {line_number}: previous_hash mismatch")
            calculated = record_hash(record)
            if record["record_hash"] != calculated:
                errors.append(f"line {line_number}: record_hash mismatch")
            previous_hash = record["record_hash"]
            last_hash = record["record_hash"]
            expected_sequence = int(record["sequence"]) + 1
            count += 1
    return {
        "valid": not errors,
        "record_count": count,
        "last_sequence": expected_sequence - 1 if count else 0,
        "last_hash": last_hash,
        "errors": errors,
    }


def write_checkpoint(audit_path: Path, checkpoint_path: Path) -> dict[str, Any]:
    verification = verify_audit(audit_path)
    checkpoint = {
        "schema_version": 1,
        "audit_path": str(audit_path),
        "last_sequence": verification["last_sequence"],
        "last_hash": verification["last_hash"],
        "checkpoint_time": utc_now(),
        "audit_valid_at_checkpoint": verification["valid"],
    }
    from .repositories import JsonRepository
    JsonRepository(checkpoint_path).write(checkpoint)
    return checkpoint


def verify_checkpoint(audit_path: Path, checkpoint_path: Path) -> dict[str, Any]:
    verification = verify_audit(audit_path)
    if not checkpoint_path.exists():
        return {"valid": False, "status": "missing", "errors": ["checkpoint not found"]}
    from .repositories import JsonRepository
    checkpoint = JsonRepository(checkpoint_path).read()
    errors = []
    if checkpoint.get("last_sequence") != verification["last_sequence"]:
        errors.append("checkpoint sequence does not match audit")
    if checkpoint.get("last_hash") != verification["last_hash"]:
        errors.append("checkpoint hash does not match audit")
    return {
        "valid": not errors and verification["valid"],
        "status": "valid" if not errors and verification["valid"] else "invalid",
        "errors": errors + verification["errors"],
        "checkpoint": checkpoint,
    }

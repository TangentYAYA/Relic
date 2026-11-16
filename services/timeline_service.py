import json
from datetime import datetime, timezone
from pathlib import Path

from domain.models import TimelineEvent
from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService


class TimelineService:
    def __init__(self, cases: CaseService):
        self.cases = cases

    def events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        event_types: set[str] | None = None,
    ) -> list[TimelineEvent]:
        case = self.cases.active_case
        if case is None:
            return []
        root = self.cases.case_path(case.case_id)
        result = self._audit_events(root)
        result.extend(self._file_events(root))
        filtered = []
        for event in result:
            parsed = _parse_timestamp(event.timestamp)
            if start and parsed < _normalise(start):
                continue
            if end and parsed > _normalise(end):
                continue
            if event_types and event.event_type not in event_types:
                continue
            filtered.append(event)
        return sorted(filtered, key=lambda event: _parse_timestamp(event.timestamp))

    def persist(self, events: list[TimelineEvent]) -> None:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before persisting timeline")
        path = self.cases.case_path(case.case_id) / "timeline.jsonl"
        for event in events:
            JsonlWriter(path).append(event.__dict__)

    def _audit_events(self, root: Path) -> list[TimelineEvent]:
        path = root.parent / "audit.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            action = record["action"]
            event_type = action.split(".", 1)[0]
            events.append(TimelineEvent(
                event_id=f"audit-{record['sequence']}",
                timestamp=record["timestamp"],
                event_type=event_type,
                source_kind="software_audit",
                summary=action,
                object_id=record["object"].get("id"),
                metadata={"action": action, "sequence": record["sequence"]},
            ))
        return events

    def _file_events(self, root: Path) -> list[TimelineEvent]:
        path = root / "files.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            for key, event_type in (
                ("modified_at", "file_modified"),
                ("accessed_at", "file_accessed"),
                ("changed_at", "file_changed"),
                ("created_at", "file_created"),
            ):
                if record.get(key):
                    events.append(TimelineEvent(
                        event_id=f"{record['entry_id']}-{event_type}",
                        timestamp=record[key],
                        event_type=event_type,
                        source_kind="filesystem",
                        summary=f"{event_type}: {record['path']}",
                        object_id=str(record.get("inode")),
                        file_path=record["path"],
                    ))
        return events


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _normalise(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)

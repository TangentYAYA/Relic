from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Partition:
    index: int
    description: str
    start_sector: int
    length_sectors: int
    end_sector: int
    allocated: bool = True
    filesystem_id: str | None = None


@dataclass
class FileSystemInfo:
    filesystem_id: str
    filesystem_type: str
    offset_sectors: int
    raw_output: str
    status: str
    block_size: int | None = None


@dataclass
class Evidence:
    evidence_id: str
    name: str
    source_path: str
    size_bytes: int
    loaded_at: str
    image_type: str = "raw"
    sha256: str | None = None
    hash_status: str = "pending"
    partitions: list[Partition] = field(default_factory=list)
    filesystems: list[FileSystemInfo] = field(default_factory=list)


@dataclass
class FileEntry:
    path: str
    name: str
    inode: int
    size_bytes: int
    entry_type: str
    mode: str
    modified_at: str | None = None
    accessed_at: str | None = None
    changed_at: str | None = None
    created_at: str | None = None
    filesystem_offset_sectors: int = 0


@dataclass
class ExportRecord:
    export_id: str
    evidence_id: str
    inode: int
    source_path: str
    destination_path: str
    size_bytes: int
    sha256: str
    exported_at: str


@dataclass
class AnalysisTask:
    task_id: str
    task_type: str
    task_name: str
    parameters: dict
    status: str = "pending"
    progress: int = 0
    start_time: str | None = None
    end_time: str | None = None
    result: dict | None = None
    error_message: str | None = None


@dataclass
class TimelineEvent:
    event_id: str
    timestamp: str
    event_type: str
    source_kind: str
    summary: str
    object_id: str | None = None
    file_path: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Case:
    case_id: str
    case_number: str
    name: str
    examiner: str
    created_at: str
    subject: str
    description: str
    status: str = "open"
    evidence_ids: list[str] = field(default_factory=list)


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value

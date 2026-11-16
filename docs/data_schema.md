# Relic 数据结构设计

所有时间使用 UTC ISO-8601 字符串，所有 ID 使用 UUID，所有哈希使用小写十六进制 SHA-256。JSON 文件采用 UTF-8。示例是结构约定，不是伪造的分析结果。

## 案件和证据

```json
{
  "schema_version": 1,
  "case_id": "uuid",
  "case_number": "CASE-2026-001",
  "name": "string",
  "examiner": "string",
  "created_at": "2026-11-16T00:00:00Z",
  "subject": "string",
  "description": "string",
  "status": "open",
  "evidence_ids": ["uuid"]
}
```

```json
{
  "schema_version": 1,
  "evidence_id": "uuid",
  "name": "disk.dd",
  "source_path": "D:\\evidence\\disk.dd",
  "size_bytes": 0,
  "loaded_at": "2026-11-16T00:00:00Z",
  "sha256": "64 lowercase hex characters",
  "hash_algorithm": "SHA-256",
  "hash_status": "baseline|verified|mismatch|pending",
  "image_type": "raw",
  "tsk_cli_version": "4.14.0",
  "partitions": [],
  "filesystems": []
}
```

`source_path` 是证据定位信息，不复制镜像。路径变化、缺失、大小变化或结束哈希不匹配均进入 warning/fail 质量结论。

## Partition 与文件系统

```json
{
  "partition_id": "uuid",
  "index": 1,
  "description": "NTFS / Basic data",
  "start_sector": 2048,
  "length_sectors": 100000,
  "end_sector": 102047,
  "sector_size": 512,
  "allocated": true,
  "filesystem_id": "uuid"
}
```

```json
{
  "filesystem_id": "uuid",
  "type": "NTFS",
  "offset_sectors": 2048,
  "block_size": 4096,
  "source_partition_id": "uuid",
  "status": "identified|unsupported|failed",
  "raw_output_sha256": "sha256"
}
```

## 文件清单 JSONL

文件 `files.jsonl` 每行一个独立对象，支持增量追加和断点恢复：

```json
{
  "schema_version": 1,
  "record_type": "file_entry",
  "entry_id": "uuid",
  "evidence_id": "uuid",
  "filesystem_id": "uuid",
  "path": "/Documents/report.txt",
  "name": "report.txt",
  "parent_path": "/Documents",
  "inode": 12345,
  "entry_type": "file|directory|link|unknown",
  "size_bytes": 1234,
  "allocated": true,
  "deleted": false,
  "mac_times": {
    "modified": "2026-01-01T00:00:00Z",
    "accessed": "2026-01-02T00:00:00Z",
    "changed": "2026-01-03T00:00:00Z",
    "created": null
  },
  "reported_type": "text/plain",
  "detected_type": "text/plain",
  "type_confidence": "signature|extension|unknown",
  "source_command": "fls",
  "source_command_version": "4.14.0",
  "created_at": "2026-11-16T00:00:00Z"
}
```

清单写入采用单 writer、追加、每行 flush；任务重启使用 `entry_id`/`inode`/path 组合去重或记录重跑批次，不覆盖原始记录。

## AnalysisTask 与 AnalysisResult

```json
{
  "task_id": "uuid",
  "task_name": "filesystem_listing",
  "parameters": {"filesystem_id": "uuid", "recursive": true},
  "status": "queued|running|succeeded|failed|cancelled",
  "progress": 0.0,
  "started_at": null,
  "ended_at": null,
  "result_id": null,
  "error": null,
  "worker": "QThreadPool"
}
```

```json
{
  "result_id": "uuid",
  "task_id": "uuid",
  "result_type": "keyword_search|file_type|exif|timeline|export",
  "status": "succeeded",
  "created_at": "2026-11-16T00:00:00Z",
  "summary": {"matched": 0},
  "artifacts": [{"path": "results/result.jsonl", "sha256": "sha256"}],
  "source_ids": ["uuid"],
  "warnings": []
}
```

## 审计 JSONL 和哈希链

`audit.jsonl` 每行：

```json
{
  "schema_version": 1,
  "sequence": 1,
  "timestamp": "2026-11-16T00:00:00Z",
  "actor": "local-user",
  "action": "evidence.hash_baseline",
  "object": {"type": "evidence", "id": "uuid"},
  "parameters_summary": {"algorithm": "SHA-256"},
  "result": {"status": "success", "sha256": "sha256"},
  "error": null,
  "previous_hash": "64 zeros for the first record",
  "record_hash": "sha256(canonical_record_without_record_hash)"
}
```

哈希输入使用固定字段顺序 `schema_version, sequence, timestamp, actor, action, object, parameters_summary, result, error, previous_hash` 的 canonical JSON、UTF-8、无空白分隔符和 `sort_keys=false`。`record_hash` 不包含自身；第一条记录的 `previous_hash` 是 64 个 ASCII `0`，后续记录引用上一条 `record_hash`。独立 `audit_checkpoint.json` 保存最后 sequence、record hash、checkpoint 时间和当时验证状态。默认位置是案件根数据目录的同级审计目录，不属于原始证据目录。哈希链能检测部分修改和尾部截断，但不能阻止拥有底层权限者重写整个日志。

## Annotation、Timeline 与 QualityCheck

注释包含 `annotation_id`, `entry_id`, `label`, `note`, `actor`, `created_at`, `updated_at`；时间线事件包含 `event_id`, `entry_id`, `event_type`, `timestamp`, `source`, `confidence`。质量检查包含 `check_id`, `name`, `status=pass|warning|incomplete`, `details`, `checked_at`，禁止把缺失真实结果标为 pass。

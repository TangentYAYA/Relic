# Relic Baseline Snapshot

Snapshot date: 2026-11-16.

This document records the version pushed before fixing the known validation
failures. No business code was changed to produce this snapshot.

## Runtime

| Component | Observed version |
|---|---|
| Windows | Windows 11 Build 26200 |
| Python | 3.11.9 |
| PySide6 | 6.12.0 |
| pytest | 9.2.0 |
| Pillow | 12.3.0 |
| PyInstaller | 6.22.3 |
| TSK CLI | 4.14.0 |

TSK executable directory:

`D:\sleuthkit\sleuthkit\bin`

Verified executables: `mmls.exe`, `fsstat.exe`, `fls.exe`, `istat.exe`,
and `icat.exe`.

## Existing validation reports

- [Functional and exception results](./test_results.md)
- [Measured performance](./performance_results.md)
- [Known limitations](./known_limitations.md)

The existing functional regression command completed with:

```text
25 passed in 3.00s
```

## SuspectData.dd evidence record

| Field | Value |
|---|---|
| Path | `D:\experiments\SuspectData.dd` |
| Size | `31,457,280` bytes |
| SHA-256 | `6baed29520499d2d5c44c32a0f3a8a08cbe92c47b4e00101b1041d14f9a579e2` |
| Detected filesystem | FAT16 |
| Filesystem offset | 0 sectors |
| File records observed | 16 |

The source file hash and last-write time were unchanged before and after the
full-flow test. Derived case data was created under a temporary case directory
and removed after testing.

## Reproduced `entry_id` failure

The full flow reached file listing successfully, writing 16 records to
`files.jsonl`. The persisted `FileEntry` keys were:

```text
accessed_at, changed_at, created_at, entry_type,
filesystem_offset_sectors, inode, mode, modified_at, name, path, size_bytes
```

`entry_id` was absent. Calling `TimelineService.events()` then failed with:

```text
KeyError: 'entry_id'
```

The same exception prevented `ReportService.generate()` from completing,
because report rendering consumes the timeline.

## Reproduced concurrent JSONL failure

Eight threads attempted to append 500 records each to one `JsonlWriter`.
Expected records: 4000. Observed:

```json
{
  "lines": 3798,
  "valid": 3797,
  "bad": 1,
  "expected": 4000
}
```

## Reproduced concurrent audit failure

Two independent `AuditWriter` instances appended to the same audit file.
The chain became invalid with:

```text
line 2: expected sequence 2, got 1
line 2: previous_hash mismatch
```

## Scope

This snapshot is a reproducible baseline, not a claim that the current
validation stage passed. The `entry_id` schema mismatch and concurrent writer
failures remain intentionally recorded for the next correction stage.

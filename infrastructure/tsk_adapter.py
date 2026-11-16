import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from domain.models import FileEntry, FileSystemInfo, Partition


class TSKError(RuntimeError):
    pass


class TSKProcessError(TSKError):
    pass


class TSKParseError(TSKError):
    pass


class TSKAdapter:
    def __init__(self, bin_dir: Path, timeout_seconds: int = 120):
        self.bin_dir = bin_dir
        self.timeout_seconds = timeout_seconds

    def _run(self, executable: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        path = self.bin_dir / f"{executable}.exe"
        if not path.is_file():
            raise TSKError(f"TSK executable not found: {path}")
        try:
            completed = subprocess.run(
                [str(path), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TSKProcessError(f"{executable} timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise TSKProcessError(f"{executable} failed ({completed.returncode}): {detail}")
        return completed

    def version(self) -> str:
        return self._run("mmls", ["-V"]).stdout.strip()

    def inspect_partitions(self, image: Path) -> list[Partition]:
        self._validate_image(image)
        output = self._run("mmls", [str(image)]).stdout
        partitions: list[Partition] = []
        for line in output.splitlines():
            match = re.match(
                r"^\s*(\S+)\s+(?:\S+\s+)?(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$", line
            )
            if not match:
                continue
            slot, start, end, length, description = match.groups()
            index = slot.rstrip(":").split(":")[-1]
            partitions.append(
                Partition(
                    index=int(index),
                    description=description.strip(),
                    start_sector=int(start),
                    length_sectors=int(length),
                    end_sector=int(end),
                    allocated="Unallocated" not in description,
                )
            )
        if not partitions:
            raise TSKParseError("mmls returned no parseable partition records")
        return partitions

    def inspect_filesystem(self, image: Path, offset_sectors: int) -> FileSystemInfo:
        self._validate_image(image)
        if offset_sectors < 0:
            raise ValueError("offset_sectors must be non-negative")
        output = self._run("fsstat", ["-o", str(offset_sectors), str(image)]).stdout
        fs_type = "unknown"
        for line in output.splitlines():
            if line.lower().startswith("file system type"):
                fs_type = line.split(":", 1)[-1].strip()
                break
        if fs_type == "unknown":
            first = next((line.strip() for line in output.splitlines() if line.strip()), "")
            fs_type = first or "unknown"
        block_match = re.search(r"block size:\s*(\d+)", output, re.IGNORECASE)
        return FileSystemInfo(
            filesystem_id=f"fs-{offset_sectors}",
            filesystem_type=fs_type,
            offset_sectors=offset_sectors,
            raw_output=output,
            status="identified",
            block_size=int(block_match.group(1)) if block_match else None,
        )

    def list_files(
        self, image: Path, offset_sectors: int, recursive: bool = False, inode: int | None = None
    ) -> list[FileEntry]:
        return list(self.iter_files(image, offset_sectors, recursive, inode))

    def iter_files(
        self, image: Path, offset_sectors: int, recursive: bool = False, inode: int | None = None
    ):
        self._validate_image(image)
        if offset_sectors < 0:
            raise ValueError("offset_sectors must be non-negative")
        arguments = ["-o", str(offset_sectors), "-m", "/", "-p"]
        if recursive:
            arguments.append("-r")
        arguments.append(str(image))
        if inode is not None:
            if inode < 0:
                raise ValueError("inode must be non-negative")
            arguments.append(str(inode))
        path = self.bin_dir / "fls.exe"
        if not path.is_file():
            raise TSKError(f"TSK executable not found: {path}")
        process = subprocess.Popen(
            [str(path), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                parsed = self._parse_fls_line(line.rstrip("\r\n"), offset_sectors)
                if parsed is not None:
                    yield parsed
            stderr = process.stderr.read() if process.stderr else ""
            return_code = process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise TSKProcessError("fls timed out") from exc
        if return_code != 0:
            raise TSKProcessError(f"fls failed ({return_code}): {stderr.strip()}")

    @staticmethod
    def _parse_fls_line(line: str, offset_sectors: int) -> FileEntry | None:
        fields = line.split("|")
        if len(fields) != 11:
            return None
        _, path, inode_text, mode, _, _, size, atime, mtime, ctime, crtime = fields
        try:
            entry_inode = int(inode_text.split("-", 1)[0])
            entry_size = int(size)
        except ValueError as exc:
            raise TSKParseError(f"invalid fls record: {line}") from exc
        return FileEntry(
            path=path,
            name=Path(path).name,
            inode=entry_inode,
            size_bytes=entry_size,
            entry_type={"r": "file", "d": "directory", "l": "link"}.get(mode[:1], "unknown"),
            mode=mode,
            modified_at=_epoch_to_iso(mtime),
            accessed_at=_epoch_to_iso(atime),
            changed_at=_epoch_to_iso(ctime),
            created_at=_epoch_to_iso(crtime),
            filesystem_offset_sectors=offset_sectors,
        )

    def stat(self, image: Path, offset_sectors: int, inode: int) -> str:
        self._validate_image(image)
        return self._run("istat", ["-o", str(offset_sectors), str(image), str(inode)]).stdout

    def extract(self, image: Path, offset_sectors: int, inode: int, destination: Path) -> int:
        self._validate_image(image)
        if offset_sectors < 0 or inode < 0:
            raise ValueError("offset and inode must be non-negative")
        executable = self.bin_dir / "icat.exe"
        if not executable.is_file():
            raise TSKError(f"TSK executable not found: {executable}")
        try:
            with destination.open("wb") as handle:
                completed = subprocess.run(
                    [str(executable), "-o", str(offset_sectors), str(image), str(inode)],
                    stdout=handle,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout_seconds,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise TSKProcessError("icat timed out") from exc
        if completed.returncode != 0:
            destination.unlink(missing_ok=True)
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise TSKProcessError(f"icat failed ({completed.returncode}): {detail}")
        return destination.stat().st_size

    @staticmethod
    def _validate_image(image: Path) -> None:
        if not image.is_file():
            raise FileNotFoundError(str(image))


def _epoch_to_iso(value: str) -> str | None:
    try:
        epoch = int(value)
    except ValueError:
        return None
    if epoch == 0:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")

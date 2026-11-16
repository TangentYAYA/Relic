import hashlib
from pathlib import Path
from typing import Callable


CHUNK_SIZE = 4 * 1024 * 1024


def sha256_file(
    path: Path,
    progress: Callable[[int], None] | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> tuple[str, int]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    digest = hashlib.sha256()
    total = path.stat().st_size
    processed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
            processed += len(chunk)
            if progress:
                progress(min(100, int(processed * 100 / total)) if total else 100)
    return digest.hexdigest(), total


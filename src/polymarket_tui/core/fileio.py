"""Atomic file writes for persisted state.

write_text/O_TRUNC truncate in place: a crash, full disk, or SIGKILL
mid-write leaves a partial file, and the loaders' tolerant JSON/TOML parsing
then silently resets the state (watchlist wiped, credentials lost). Writing
a temp file in the same directory and os.replace()-ing it in is atomic on
POSIX - the old content survives any failure before the rename.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path


def write_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    """Write `text` to `path` atomically. `mode` applies to the new file -
    secrets pass 0o600 so the content is never readable more loosely, even
    transiently (os.replace carries the temp file's permissions over)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()  # a stale temp must not survive with old permissions
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()

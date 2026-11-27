from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

CHUNK = 1024 * 1024
IGNORED_NAMES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    ".git",
    ".gitignore",
    ".gitattributes",
    ".retro-save-sync-state.json",
}
IGNORED_DIR_NAMES = {".git", ".rclone", "__pycache__"}
CHICAGO = ZoneInfo("America/Chicago")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_mtime_ns(path: Path) -> int:
    return path.stat().st_mtime_ns


def format_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def now_local() -> datetime:
    return datetime.now(CHICAGO)


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def stamp_now() -> str:
    return now_local().strftime("%Y%m%d-%H%M%S")


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def should_ignore(path: Path) -> bool:
    name = path.name.lower()
    if name in IGNORED_NAMES or name.endswith(".tmp") or name.endswith("~"):
        return True
    if name.startswith("._"):
        return True
    return False


def iter_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if should_ignore(path) or not path.is_file() or path.is_symlink():
                continue
            yield path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_file(src: Path, dest: Path) -> None:
    ensure_dir(dest.parent)
    data = src.read_bytes()
    tmp = dest.with_name(dest.name + ".rss-tmp")
    tmp.write_bytes(data)
    os.utime(tmp, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns))
    tmp.replace(dest)


def safe_backup_id(stamp: str | None = None) -> str:
    raw = stamp or stamp_now()
    if not re.fullmatch(r"\d{8}-\d{6}(?:-[a-zA-Z0-9]+)?", raw):
        raise ValueError(f"invalid backup id: {raw}")
    return raw


def monotonic_stamp(existing: set[str]) -> str:
    base = stamp_now()
    if base not in existing:
        return base
    # Same-second collision: append a suffix.
    for i in range(1, 1000):
        candidate = f"{base}-{i:02d}"
        if candidate not in existing:
            return candidate
    return f"{base}-{int(time.time_ns() % 10_000)}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

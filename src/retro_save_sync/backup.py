from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from retro_save_sync.models import FileRecord, PlanItem
from retro_save_sync.util import copy_file, ensure_dir, now_iso, sha256_file, monotonic_stamp, safe_backup_id


@dataclass
class BackupFile:
    profile_id: str
    kind: str
    relpath: str
    original_path: str
    sha256: str
    size: int
    mtime_ns: int
    action: str
    stored_as: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "kind": self.kind,
            "relpath": self.relpath,
            "original_path": self.original_path,
            "sha256": self.sha256,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "action": self.action,
            "stored_as": self.stored_as,
        }


@dataclass
class Backup:
    id: str
    created: str
    operation: str
    target_type: str
    target_path: str
    files: list[BackupFile] = field(default_factory=list)
    path: Optional[Path] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created": self.created,
            "operation": self.operation,
            "target_type": self.target_type,
            "target_path": self.target_path,
            "files": [f.as_dict() for f in self.files],
        }


def _existing_ids(backup_root: Path) -> set[str]:
    if not backup_root.is_dir():
        return set()
    return {p.name for p in backup_root.iterdir() if p.is_dir()}


def _overwrite_record(item: PlanItem) -> FileRecord | None:
    if not item.will_overwrite:
        return None
    if item.action == "push":
        return item.remote
    if item.action == "pull":
        return item.local
    return None


def create_backup(
    backup_root: Path,
    items: list[PlanItem],
    *,
    operation: str,
    target_type: str,
    target_path: str,
) -> Backup | None:
    """Snapshot every file that is about to be overwritten.

    Layout: backups/<YYYYMMDD-HHMMSS>/<profile>/<kind>/<relpath>
    """
    to_save: list[tuple[PlanItem, FileRecord]] = []
    for item in items:
        record = _overwrite_record(item)
        if record is None:
            continue
        if not record.path.is_file():
            continue
        to_save.append((item, record))
    if not to_save:
        return None

    ensure_dir(backup_root)
    backup_id = monotonic_stamp(_existing_ids(backup_root))
    dest_root = backup_root / backup_id
    ensure_dir(dest_root)

    files: list[BackupFile] = []
    for item, record in to_save:
        stored_as = f"{record.profile_id}/{record.kind}/{record.relpath}"
        stored_path = dest_root / stored_as
        copy_file(record.path, stored_path)
        stored_hash = sha256_file(stored_path)
        if stored_hash != record.sha256:
            # Re-hash source in case it raced; the snapshot must match what we copied.
            record.sha256 = stored_hash
        files.append(
            BackupFile(
                profile_id=record.profile_id,
                kind=record.kind,
                relpath=record.relpath,
                original_path=str(record.path),
                sha256=stored_hash,
                size=stored_path.stat().st_size,
                mtime_ns=record.mtime_ns,
                action=item.action,
                stored_as=stored_as,
            )
        )

    backup = Backup(
        id=backup_id,
        created=now_iso(),
        operation=operation,
        target_type=target_type,
        target_path=target_path,
        files=files,
        path=dest_root,
    )
    manifest = dest_root / "manifest.json"
    manifest.write_text(json.dumps(backup.as_dict(), indent=2) + "\n", encoding="utf-8")
    return backup


def load_backup(backup_root: Path, backup_id: str) -> Backup:
    safe_backup_id(backup_id)
    dest_root = backup_root / backup_id
    manifest = dest_root / "manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"backup not found: {backup_id}")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    files = [BackupFile(**entry) for entry in raw.get("files") or []]
    return Backup(
        id=raw["id"],
        created=raw.get("created") or "",
        operation=raw.get("operation") or "",
        target_type=raw.get("target_type") or "",
        target_path=raw.get("target_path") or "",
        files=files,
        path=dest_root,
    )


def list_backups(backup_root: Path) -> list[Backup]:
    if not backup_root.is_dir():
        return []
    backups: list[Backup] = []
    for child in sorted(backup_root.iterdir(), reverse=True):
        if child.is_dir() and (child / "manifest.json").is_file():
            try:
                backups.append(load_backup(backup_root, child.name))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return backups


class RestoreError(RuntimeError):
    def __init__(self, message: str, mismatches: list[dict] | None = None):
        super().__init__(message)
        self.mismatches = mismatches or []


def restore_backup(backup_root: Path, backup_id: str, *, verify: bool = True) -> dict[str, Any]:
    """Restore every snapshotted file to its original path and verify SHA-256."""
    backup = load_backup(backup_root, backup_id)
    assert backup.path is not None
    restored: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for entry in backup.files:
        source = backup.path / entry.stored_as
        if not source.is_file():
            raise RestoreError(f"missing snapshot file: {entry.stored_as}")
        dest = Path(entry.original_path)
        copy_file(source, dest)
        actual = sha256_file(dest)
        info = {
            "path": str(dest),
            "expected": entry.sha256,
            "actual": actual,
            "ok": actual == entry.sha256,
        }
        restored.append(info)
        if actual != entry.sha256:
            mismatches.append(info)
    if verify and mismatches:
        raise RestoreError(
            f"SHA-256 verification failed for {len(mismatches)} file(s) in backup {backup_id}",
            mismatches=mismatches,
        )
    return {
        "id": backup.id,
        "restored": restored,
        "count": len(restored),
        "verified": not mismatches,
    }

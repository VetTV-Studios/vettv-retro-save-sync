from __future__ import annotations

import json
from pathlib import Path

from retro_save_sync.backup import list_backups, load_backup, restore_backup
from retro_save_sync.demo import write_dummy
from retro_save_sync.engine import apply_plan
from retro_save_sync.util import sha256_file


def test_timestamped_backup_before_overwrite_and_sha256_restore(linux_cfg):
    first = apply_plan(linux_cfg, dry_run=False)
    assert first.backup is None

    local = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    remote = Path(linux_cfg.target.path) / "retroarch/saves/Neon Circuit.srm"
    original_remote_hash = sha256_file(remote)
    original_remote_bytes = remote.read_bytes()
    write_dummy(local, b"updated-local-bytes\n", size=2048)
    new_hash = sha256_file(local)
    assert new_hash != original_remote_hash

    second = apply_plan(linux_cfg, dry_run=False)
    assert second.backup is not None
    backup = load_backup(linux_cfg.dirs.backup_dir, second.backup.id)
    assert backup.id == second.backup.id
    assert (linux_cfg.dirs.backup_dir / backup.id / "manifest.json").is_file()
    # Path layout: backups/<stamp>/<profile>/...
    snap = linux_cfg.dirs.backup_dir / backup.id / "retroarch/saves/Neon Circuit.srm"
    assert snap.is_file()
    assert sha256_file(snap) == original_remote_hash
    manifest = json.loads((linux_cfg.dirs.backup_dir / backup.id / "manifest.json").read_text())
    entry = next(f for f in manifest["files"] if f["relpath"].endswith("Neon Circuit.srm"))
    assert entry["sha256"] == original_remote_hash
    assert entry["action"] == "push"
    assert Path(entry["original_path"]) == remote.resolve() or Path(entry["original_path"]) == remote

    # Target now holds the new local content.
    assert sha256_file(remote) == new_hash

    # Rollback restore brings the exact prior bytes back and verifies SHA-256.
    result = restore_backup(linux_cfg.dirs.backup_dir, backup.id, verify=True)
    assert result["verified"] is True
    assert result["count"] >= 1
    assert sha256_file(remote) == original_remote_hash
    assert remote.read_bytes() == original_remote_bytes


def test_pull_overwrite_snapshots_the_local_file(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    local = linux_cfg.root / ".config/retroarch/saves/Penguin Quest.srm"
    remote = Path(linux_cfg.target.path) / "retroarch/saves/Penguin Quest.srm"
    original_local = sha256_file(local)
    write_dummy(remote, b"newer-on-target\n", size=2048)

    result = apply_plan(linux_cfg, dry_run=False)
    assert result.backup is not None
    snap = linux_cfg.dirs.backup_dir / result.backup.id / "retroarch/saves/Penguin Quest.srm"
    assert snap.is_file()
    assert sha256_file(snap) == original_local
    assert sha256_file(local) == sha256_file(remote)

    restore_backup(linux_cfg.dirs.backup_dir, result.backup.id, verify=True)
    assert sha256_file(local) == original_local


def test_list_backups_newest_first(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    local = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    write_dummy(local, b"edit-1\n", size=2048)
    a = apply_plan(linux_cfg, dry_run=False)
    write_dummy(local, b"edit-2\n", size=2048)
    b = apply_plan(linux_cfg, dry_run=False)
    listed = list_backups(linux_cfg.dirs.backup_dir)
    ids = [bk.id for bk in listed]
    assert a.backup.id in ids and b.backup.id in ids
    # Directory names are time-sortable; newest first.
    assert ids == sorted(ids, reverse=True)

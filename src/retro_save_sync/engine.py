from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from retro_save_sync.backup import Backup, create_backup
from retro_save_sync.config import AppConfig, SyncTarget
from retro_save_sync.detect import detect_profiles
from retro_save_sync.models import FileRecord, PlanItem, Profile, SyncPlan
from retro_save_sync.targets import GitTargetError, apply_git_side_effects, prepare_git_target
from retro_save_sync.util import copy_file, ensure_dir, file_mtime_ns, iter_files, now_iso, posix_rel, sha256_file


def _index_files(profiles: list[Profile]) -> dict[str, FileRecord]:
    records: dict[str, FileRecord] = {}
    for profile in profiles:
        if not profile.present:
            continue
        for root in profile.roots:
            if not root.path.is_dir():
                continue
            for path in iter_files(root.path):
                rel = posix_rel(path, root.path)
                record = FileRecord(
                    profile_id=profile.id,
                    kind=root.kind,
                    relpath=rel,
                    path=path,
                    sha256=sha256_file(path),
                    mtime_ns=file_mtime_ns(path),
                    size=path.stat().st_size,
                )
                records[record.key] = record
    return records


def remote_file_path(target_root: Path, record_key_parts: tuple[str, str, str]) -> Path:
    profile_id, kind, relpath = record_key_parts
    return target_root / profile_id / kind / Path(relpath)


def _index_remote(target_root: Path) -> dict[str, FileRecord]:
    records: dict[str, FileRecord] = {}
    if not target_root.is_dir():
        return records
    for profile_dir in target_root.iterdir():
        if not profile_dir.is_dir() or profile_dir.name.startswith("."):
            continue
        for kind_dir in profile_dir.iterdir():
            if not kind_dir.is_dir() or kind_dir.name.startswith("."):
                continue
            for path in iter_files(kind_dir):
                rel = posix_rel(path, kind_dir)
                record = FileRecord(
                    profile_id=profile_dir.name,
                    kind=kind_dir.name,
                    relpath=rel,
                    path=path,
                    sha256=sha256_file(path),
                    mtime_ns=file_mtime_ns(path),
                    size=path.stat().st_size,
                )
                records[record.key] = record
    return records


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "files": {}, "updated": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "files": {}, "updated": None}
    data.setdefault("version", 1)
    data.setdefault("files", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    state["updated"] = now_iso()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _last_hash(state: dict[str, Any], key: str) -> str | None:
    entry = (state.get("files") or {}).get(key)
    if not entry:
        return None
    if isinstance(entry, str):
        return entry
    return entry.get("sha256")


def classify_pair(
    key: str,
    local: FileRecord | None,
    remote: FileRecord | None,
    last_hash: str | None,
) -> PlanItem:
    profile_id, kind, relpath = _split_key(key)
    if local and remote and local.sha256 == remote.sha256:
        return PlanItem(
            action="skip",
            profile_id=profile_id,
            kind=kind,
            relpath=relpath,
            reason="identical SHA-256 on both sides",
            local=local,
            remote=remote,
            will_overwrite=False,
        )
    if local and not remote:
        return PlanItem(
            action="push",
            profile_id=profile_id,
            kind=kind,
            relpath=relpath,
            reason="present only on local",
            local=local,
            remote=None,
            will_overwrite=False,
        )
    if remote and not local:
        return PlanItem(
            action="pull",
            profile_id=profile_id,
            kind=kind,
            relpath=relpath,
            reason="present only on target",
            local=None,
            remote=remote,
            will_overwrite=False,
        )

    assert local is not None and remote is not None
    # Hashes differ. Use last-sync hash for a three-way decision so we never
    # silently clobber a newer or independently-changed save.
    if last_hash:
        local_changed = local.sha256 != last_hash
        remote_changed = remote.sha256 != last_hash
        if local_changed and not remote_changed:
            return PlanItem(
                action="push",
                profile_id=profile_id,
                kind=kind,
                relpath=relpath,
                reason="local changed since last sync; target still matches last sync",
                local=local,
                remote=remote,
                will_overwrite=True,
            )
        if remote_changed and not local_changed:
            return PlanItem(
                action="pull",
                profile_id=profile_id,
                kind=kind,
                relpath=relpath,
                reason="target changed since last sync; local still matches last sync",
                local=local,
                remote=remote,
                will_overwrite=True,
            )
        return PlanItem(
            action="conflict",
            profile_id=profile_id,
            kind=kind,
            relpath=relpath,
            reason="both sides changed since last sync (SHA-256 differs)",
            local=local,
            remote=remote,
            will_overwrite=False,
        )

    # No last-sync hash. Never guess: differing content is a conflict, even
    # if one mtime is newer — a clock skew should not clobber a save.
    newer = "local" if local.mtime_ns > remote.mtime_ns else "target" if remote.mtime_ns > local.mtime_ns else "neither"
    return PlanItem(
        action="conflict",
        profile_id=profile_id,
        kind=kind,
        relpath=relpath,
        reason=f"SHA-256 differs and no last-sync hash is on file (mtime newer: {newer})",
        local=local,
        remote=remote,
        will_overwrite=False,
    )


def _split_key(key: str) -> tuple[str, str, str]:
    profile_id, kind, relpath = key.split("/", 2)
    return profile_id, kind, relpath


def build_plan(
    local_index: dict[str, FileRecord],
    remote_index: dict[str, FileRecord],
    state: dict[str, Any],
    *,
    target_type: str,
    target_path: str,
    notes: list[str] | None = None,
) -> SyncPlan:
    keys = sorted(set(local_index) | set(remote_index))
    items = [
        classify_pair(key, local_index.get(key), remote_index.get(key), _last_hash(state, key))
        for key in keys
    ]
    return SyncPlan(
        items=items,
        target_type=target_type,
        target_path=target_path,
        notes=list(notes or []),
    )


@dataclass
class ScanResult:
    profiles: list[Profile]
    local_index: dict[str, FileRecord]
    config: AppConfig


def scan(config: AppConfig, include_missing: bool = True) -> ScanResult:
    profiles = detect_profiles(
        config.root,
        config.platform,
        custom_profiles=config.custom_profiles,
        include_missing=include_missing,
    )
    index = _index_files(profiles)
    return ScanResult(profiles=profiles, local_index=index, config=config)


@dataclass
class ApplyResult:
    plan: SyncPlan
    applied: list[PlanItem] = field(default_factory=list)
    skipped_conflicts: list[PlanItem] = field(default_factory=list)
    backup: Backup | None = None
    dry_run: bool = False
    git: dict[str, Any] | None = None
    rclone: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "summary": self.plan.summary(),
            "applied": [i.as_dict() for i in self.applied],
            "conflicts": [i.as_dict() for i in self.skipped_conflicts],
            "backup_id": None if self.backup is None else self.backup.id,
            "git": self.git,
            "rclone": self.rclone,
        }


def preview(config: AppConfig, target: SyncTarget | None = None) -> SyncPlan:
    target = target or config.target
    scan_result = scan(config, include_missing=True)
    target_root, notes = _prepare_target(config, target, for_write=False)
    remote_index = _index_remote(target_root) if target_root is not None else {}
    state = load_state(config.dirs.state_path)
    display = target.display_path()
    if target_root is not None and target.type != "rclone":
        display = str(target_root)
    return build_plan(
        scan_result.local_index,
        remote_index,
        state,
        target_type=target.type,
        target_path=display,
        notes=notes,
    )


def _prepare_target(
    config: AppConfig, target: SyncTarget, *, for_write: bool
) -> tuple[Path | None, list[str]]:
    notes: list[str] = []
    if target.type == "rclone":
        from retro_save_sync.targets import rclone_available, resolve_rclone_staging

        if not rclone_available():
            notes.append("rclone is not installed; the rclone target is unavailable.")
            return None, notes
        if not (target.remote or target.path):
            notes.append("rclone remote is not configured.")
            return None, notes
        staging, extra = resolve_rclone_staging(config, target, for_write=for_write, notes=notes)
        notes.extend(extra)
        return staging, notes

    if not target.path:
        notes.append("No sync target path is configured.")
        return None, notes

    path = Path(target.path).expanduser()
    if target.type == "git":
        try:
            worktree, extra = prepare_git_target(path, config.dirs.cache_dir, fetch=True)
            notes.extend(extra)
            return worktree, notes
        except GitTargetError as exc:
            notes.append(str(exc))
            return None, notes

    # folder target (also covers a mounted Drive/OneDrive/NAS/USB path)
    if for_write:
        ensure_dir(path)
    elif not path.exists():
        notes.append(f"Folder target does not exist yet: {path}")
    return path.resolve() if path.exists() else path, notes


def apply_plan(
    config: AppConfig,
    plan: SyncPlan | None = None,
    *,
    dry_run: bool = False,
    target: SyncTarget | None = None,
) -> ApplyResult:
    target = target or config.target
    if plan is None:
        plan = preview(config, target)
    result = ApplyResult(plan=plan, dry_run=dry_run, skipped_conflicts=list(plan.conflicts))

    if target.type == "rclone" and not dry_run:
        # rclone apply is handled after we sync the staging folder.
        pass

    if dry_run:
        return result

    if any("not configured" in n or "not installed" in n or "does not exist" in n for n in plan.notes) and not target.path and target.type != "rclone":
        raise RuntimeError("Cannot sync: " + "; ".join(plan.notes))
    if target.type != "rclone" and not target.path:
        raise RuntimeError("Cannot sync: no target path configured.")

    target_root, notes = _prepare_target(config, target, for_write=True)
    plan.notes.extend(n for n in notes if n not in plan.notes)
    if target_root is None:
        raise RuntimeError("Cannot sync: " + ("; ".join(plan.notes) or "target unavailable"))

    # Re-index remote against the prepared work tree (git clone / rclone staging).
    if target.type in {"git", "rclone"}:
        scan_result = scan(config, include_missing=True)
        state = load_state(config.dirs.state_path)
        plan = build_plan(
            scan_result.local_index,
            _index_remote(target_root),
            state,
            target_type=target.type,
            target_path=target.display_path(),
            notes=plan.notes,
        )
        result.plan = plan
        result.skipped_conflicts = list(plan.conflicts)

    overwrites = [i for i in plan.items if i.will_overwrite and i.action in {"push", "pull"}]
    if overwrites:
        result.backup = create_backup(
            config.dirs.backup_dir,
            overwrites,
            operation="sync",
            target_type=target.type,
            target_path=target.display_path(),
        )

    state = load_state(config.dirs.state_path)
    applied: list[PlanItem] = []
    for item in plan.items:
        if item.action == "conflict" or item.action == "skip":
            continue
        if item.action == "push" and item.local is not None:
            dest = remote_file_path(target_root, (item.profile_id, item.kind, item.relpath))
            copy_file(item.local.path, dest)
            _remember(state, item.key, item.local.sha256)
            applied.append(item)
        elif item.action == "pull" and item.remote is not None:
            dest = _local_dest(config, item)
            if dest is None:
                plan.notes.append(
                    f"Cannot pull {item.key}: no local profile root for this file."
                )
                continue
            copy_file(item.remote.path, dest)
            _remember(state, item.key, item.remote.sha256)
            applied.append(item)
    save_state(config.dirs.state_path, state)
    result.applied = applied

    if target.type == "git":
        result.git = apply_git_side_effects(target_root, target, message=_commit_message(applied))
    if target.type == "rclone":
        from retro_save_sync.targets import rclone_push_staging

        result.rclone = rclone_push_staging(config, target, target_root, dry_run=False)
    return result


def _remember(state: dict[str, Any], key: str, sha: str) -> None:
    files = state.setdefault("files", {})
    files[key] = {"sha256": sha, "synced_at": now_iso()}


def _local_dest(config: AppConfig, item: PlanItem) -> Path | None:
    profiles = detect_profiles(
        config.root,
        config.platform,
        custom_profiles=config.custom_profiles,
        include_missing=True,
    )
    for profile in profiles:
        if profile.id != item.profile_id:
            continue
        for root in profile.roots:
            if root.kind == item.kind:
                return root.path / item.relpath
    return None


def _commit_message(applied: list[PlanItem]) -> str:
    pushes = sum(1 for i in applied if i.action == "push")
    pulls = sum(1 for i in applied if i.action == "pull")
    return f"retro-save-sync: {pushes} pushed, {pulls} pulled"

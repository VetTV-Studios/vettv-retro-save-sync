"""Sync target adapters: folder (implicit in the engine), Git, and rclone."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from retro_save_sync.config import AppConfig, SyncTarget
from retro_save_sync.util import ensure_dir

GIT_IDENTITY = [
    "-c",
    "user.name=Retro Save Sync",
    "-c",
    "user.email=retro-save-sync@vettv.local",
]


class GitTargetError(RuntimeError):
    pass


class RcloneTargetError(RuntimeError):
    pass


def run(cmd: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def git_available() -> bool:
    return shutil.which("git") is not None


def rclone_available() -> bool:
    return shutil.which("rclone") is not None


def _git(args: Sequence[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    if not git_available():
        raise GitTargetError("git is not installed")
    result = run(["git", *GIT_IDENTITY, *args], cwd=cwd, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitTargetError(detail or f"git {' '.join(args)} failed ({result.returncode})")
    return result


def _is_git_repo(path: Path) -> bool:
    if not path.exists():
        return False
    result = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _is_bare_repo(path: Path) -> bool:
    if not path.exists():
        return False
    result = run(["git", "rev-parse", "--is-bare-repository"], cwd=path, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def prepare_git_target(path: Path, cache_dir: Path, *, fetch: bool = True) -> tuple[Path, list[str]]:
    """Return a working tree for the configured git target.

    * If `path` is a work tree, use it (and pull if a remote exists).
    * If `path` is a bare repo, clone/update a cached work tree that tracks it.
    * If `path` does not exist, initialize a new repo there.
    """
    notes: list[str] = []
    path = path.expanduser()
    if _is_bare_repo(path):
        worktree = cache_dir / "git-worktrees" / _safe_name(path)
        if worktree.exists() and _is_git_repo(worktree):
            if fetch:
                _git(["fetch", "origin"], cwd=worktree, check=False)
                _ff_or_reset_from_origin(worktree, notes)
        else:
            if worktree.exists():
                shutil.rmtree(worktree)
            ensure_dir(worktree.parent)
            _git(["clone", str(path), str(worktree)])
        return worktree.resolve(), notes

    if path.exists() and not path.is_dir():
        raise GitTargetError(f"git target is not a directory: {path}")

    if not path.exists():
        ensure_dir(path)
        _git(["init"], cwd=path)
        notes.append(f"Initialized new git repository at {path}")
        return path.resolve(), notes

    if not _is_git_repo(path):
        _git(["init"], cwd=path)
        notes.append(f"Initialized git repository in existing folder {path}")

    if fetch:
        remotes = _git(["remote"], cwd=path, check=False)
        if remotes.returncode == 0 and remotes.stdout.strip():
            _git(["fetch", "--all"], cwd=path, check=False)
            _ff_or_reset_from_origin(path, notes)
    return path.resolve(), notes


def _ff_or_reset_from_origin(worktree: Path, notes: list[str]) -> None:
    """Update the work tree from origin without merging local unsynced files.

    File-level conflicts are owned by the engine, not git merge.
    We only fast-forward when the work tree is clean and a remote branch exists.
    """
    status = _git(["status", "--porcelain"], cwd=worktree, check=False)
    if status.stdout.strip():
        notes.append("Git work tree has local changes; skipped automatic pull.")
        return
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        probe = _git(["rev-parse", "--verify", ref], cwd=worktree, check=False)
        if probe.returncode == 0:
            _git(["merge", "--ff-only", ref], cwd=worktree, check=False)
            return


def apply_git_side_effects(worktree: Path, target: SyncTarget, message: str) -> dict[str, Any]:
    """Stage, commit, and optionally push after the folder sync has written files."""
    _git(["add", "-A"], cwd=worktree)
    status = _git(["status", "--porcelain"], cwd=worktree)
    if not status.stdout.strip():
        pushed = _maybe_push(worktree, target)
        return {"committed": False, "reason": "no changes", "pushed": pushed, "log": status.stdout}

    # First commit may need a branch name.
    head = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree, check=False)
    if head.returncode != 0 or head.stdout.strip() in {"", "HEAD"}:
        _git(["checkout", "-B", "main"], cwd=worktree, check=False)

    commit = _git(["commit", "-m", message], cwd=worktree)
    pushed = _maybe_push(worktree, target)
    return {
        "committed": True,
        "message": message,
        "log": (commit.stdout or "").strip(),
        "pushed": pushed,
    }


def _maybe_push(worktree: Path, target: SyncTarget) -> bool:
    remotes = _git(["remote"], cwd=worktree, check=False)
    names = remotes.stdout.split()
    if not names:
        return False
    remote = target.git_remote if target.git_remote in names else names[0]
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree, check=False)
    ref = branch.stdout.strip() if branch.returncode == 0 else "main"
    result = _git(["push", "-u", remote, ref], cwd=worktree, check=False)
    return result.returncode == 0


def _safe_name(path: Path) -> str:
    text = str(path.resolve()).replace(":", "_").replace("/", "_").replace("\\", "_")
    return text.strip("_") or "repo"


# --- rclone -----------------------------------------------------------------

SAFE_DENIED_REMOTES = {"/", "", ".", "~"}


def rclone_cmd() -> str:
    exe = shutil.which("rclone")
    if not exe:
        raise RcloneTargetError("rclone is not installed")
    return exe


def _validate_rclone_spec(spec: str) -> str:
    cleaned = spec.strip()
    if cleaned in SAFE_DENIED_REMOTES or cleaned.startswith("/../") or cleaned == "..":
        raise RcloneTargetError(f"refusing unsafe rclone destination: {spec!r}")
    if cleaned.startswith("-"):
        raise RcloneTargetError(f"refusing rclone destination that looks like a flag: {spec!r}")
    return cleaned


def resolve_rclone_staging(
    config: AppConfig,
    target: SyncTarget,
    *,
    for_write: bool,
    notes: list[str] | None = None,
) -> tuple[Path, list[str]]:
    """Mirror a remote into a local staging folder so the engine can plan/apply."""
    notes = list(notes or [])
    remote = _validate_rclone_spec(target.remote or target.path)
    staging = config.dirs.cache_dir / "rclone-staging" / _safe_name(Path(remote.replace(":", "_")))
    ensure_dir(staging)
    # Always pull a dry-run-safe copy of the remote first so preview/apply
    # can do SHA-256 comparison locally. copy (not sync) never deletes staging.
    args = [rclone_cmd(), "copy", remote, str(staging), "--verbose"]
    if not for_write:
        # Preview still needs current remote contents, so we copy for real into staging.
        pass
    try:
        result = run(args, check=False)
        if result.returncode != 0:
            notes.append((result.stderr or result.stdout or "rclone copy from remote failed").strip())
        else:
            notes.append(f"rclone staging updated from {remote}")
    except FileNotFoundError:
        notes.append("rclone is not installed")
    return staging, notes


def rclone_dry_run(source: str, dest: str) -> dict[str, Any]:
    exe = rclone_cmd()
    dest = _validate_rclone_spec(dest)
    source = _validate_rclone_spec(source)
    result = run([exe, "copy", source, dest, "--dry-run", "-v"], check=False)
    return {
        "available": True,
        "cmd": ["rclone", "copy", source, dest, "--dry-run", "-v"],
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }


def rclone_push_staging(
    config: AppConfig,
    target: SyncTarget,
    staging: Path,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    del config  # reserved for future flags / excludes
    remote = _validate_rclone_spec(target.remote or target.path)
    exe = rclone_cmd()
    cmd = [exe, "copy", str(staging), remote, "-v"]
    if dry_run:
        cmd.append("--dry-run")
    result = run(cmd, check=False)
    return {
        "available": True,
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
        "dry_run": dry_run,
    }


def rclone_status() -> dict[str, Any]:
    if not rclone_available():
        return {"available": False, "message": "rclone is not installed; folder and git targets still work."}
    version = run([rclone_cmd(), "version"], check=False)
    return {
        "available": True,
        "version": (version.stdout or "").splitlines()[0] if version.returncode == 0 else "rclone",
    }

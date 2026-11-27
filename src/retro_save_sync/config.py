from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from retro_save_sync.models import PlatformName, TargetType
from retro_save_sync.paths import UserDirs, detect_platform, user_dirs
from retro_save_sync.util import ensure_dir

DEFAULT_CONFIG = {
    "root_override": None,
    "platform": None,
    "backup_root": None,
    "custom_profiles": [],
    "target": {"type": "folder", "path": ""},
}


@dataclass
class SyncTarget:
    type: TargetType = "folder"
    path: str = ""
    # rclone remote, e.g. "gdrive:vettv-saves"
    remote: str = ""
    # git remote name, default "origin"
    git_remote: str = "origin"
    extra: dict[str, Any] = field(default_factory=dict)

    def display_path(self) -> str:
        if self.type == "rclone":
            return self.remote or self.path or "(rclone not configured)"
        return self.path or "(not set)"

    def as_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "path": self.path,
            "remote": self.remote,
            "git_remote": self.git_remote,
        }
        data.update(self.extra)
        return data


@dataclass
class AppConfig:
    dirs: UserDirs
    custom_profiles: list[dict] = field(default_factory=list)
    target: SyncTarget = field(default_factory=SyncTarget)
    path: Optional[Path] = None

    @property
    def root(self) -> Path:
        return self.dirs.root

    @property
    def platform(self) -> PlatformName:
        return self.dirs.platform

    def as_dict(self) -> dict[str, Any]:
        return {
            "root_override": str(self.dirs.root),
            "platform": self.dirs.platform,
            "backup_root": str(self.dirs.backup_dir),
            "custom_profiles": self.custom_profiles,
            "target": self.target.as_dict(),
        }

    def save(self, path: Path | None = None) -> Path:
        dest = path or self.path or (self.dirs.config_dir / "config.json")
        ensure_dir(dest.parent)
        dest.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")
        self.path = dest
        return dest


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_config_path(explicit: str | Path | None, dirs: UserDirs) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("RETRO_SAVE_SYNC_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return dirs.config_dir / "config.json"


def load_config(
    config_path: str | Path | None = None,
    root: str | Path | None = None,
    platform: str | None = None,
    backup_root: str | Path | None = None,
) -> AppConfig:
    platform_name = detect_platform(platform)
    # First pass: locate config using a tentative root, then honor overrides inside it.
    tentative_root = Path(root).expanduser().resolve() if root else None
    tentative = user_dirs(root=tentative_root, platform=platform_name, backup_root=Path(backup_root) if backup_root else None)
    path = resolve_config_path(config_path, tentative)
    raw = _load_json(path) if path.is_file() else {}

    root_override = root or raw.get("root_override") or None
    platform_name = detect_platform(platform or raw.get("platform"))
    backup_override = backup_root or raw.get("backup_root") or None
    dirs = user_dirs(
        root=Path(root_override).expanduser() if root_override else tentative_root,
        platform=platform_name,
        backup_root=Path(backup_override).expanduser() if backup_override else None,
    )
    target_raw = raw.get("target") or {}
    target = SyncTarget(
        type=target_raw.get("type") or "folder",
        path=str(target_raw.get("path") or ""),
        remote=str(target_raw.get("remote") or ""),
        git_remote=str(target_raw.get("git_remote") or "origin"),
    )
    return AppConfig(
        dirs=dirs,
        custom_profiles=list(raw.get("custom_profiles") or []),
        target=target,
        path=path if path.is_file() else path,
    )

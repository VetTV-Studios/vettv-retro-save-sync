"""Cross-platform emulator save-path maps (Linux/SteamOS + Windows).

All locations are resolved from an overrideable user root so tests can
point at a synthetic home without touching a real user profile.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from retro_save_sync.models import PlatformName, SaveRoot

# Built-in emulator path maps. Each kind lists candidates in priority order.
# Paths are relative to the platform user root (HOME / USERPROFILE).

LINUX_PROFILES: list[dict] = [
    {
        "id": "retroarch",
        "name": "RetroArch",
        "emulator": "retroarch",
        "variant": "native",
        "kinds": {
            "saves": [".config/retroarch/saves"],
            "states": [".config/retroarch/states"],
        },
    },
    {
        "id": "retroarch-flatpak",
        "name": "RetroArch (Flatpak)",
        "emulator": "retroarch",
        "variant": "flatpak",
        "flatpak_id": "org.libretro.RetroArch",
        "kinds": {
            "saves": [".var/app/org.libretro.RetroArch/config/retroarch/saves"],
            "states": [".var/app/org.libretro.RetroArch/config/retroarch/states"],
        },
    },
    {
        "id": "pcsx2",
        "name": "PCSX2",
        "emulator": "pcsx2",
        "variant": "native",
        "kinds": {
            "memcards": [
                ".config/PCSX2/memcards",
                ".local/share/PCSX2/memcards",
                "Documents/PCSX2/memcards",
            ],
            "sstates": [
                ".config/PCSX2/sstates",
                ".local/share/PCSX2/sstates",
                "Documents/PCSX2/sstates",
            ],
        },
    },
    {
        "id": "pcsx2-flatpak",
        "name": "PCSX2 (Flatpak)",
        "emulator": "pcsx2",
        "variant": "flatpak",
        "flatpak_id": "net.pcsx2.PCSX2",
        "kinds": {
            "memcards": [
                ".var/app/net.pcsx2.PCSX2/config/PCSX2/memcards",
                ".var/app/net.pcsx2.PCSX2/data/PCSX2/memcards",
            ],
            "sstates": [
                ".var/app/net.pcsx2.PCSX2/config/PCSX2/sstates",
                ".var/app/net.pcsx2.PCSX2/data/PCSX2/sstates",
            ],
        },
    },
    {
        "id": "dolphin",
        "name": "Dolphin",
        "emulator": "dolphin",
        "variant": "native",
        "kinds": {
            "GC": [".local/share/dolphin-emu/GC", ".config/dolphin-emu/GC"],
            "Wii": [".local/share/dolphin-emu/Wii", ".config/dolphin-emu/Wii"],
        },
    },
    {
        "id": "dolphin-flatpak",
        "name": "Dolphin (Flatpak)",
        "emulator": "dolphin",
        "variant": "flatpak",
        "flatpak_id": "org.dolphin_emu.dolphin-emu",
        "kinds": {
            "GC": [".var/app/org.dolphin_emu.dolphin-emu/data/dolphin-emu/GC"],
            "Wii": [".var/app/org.dolphin_emu.dolphin-emu/data/dolphin-emu/Wii"],
        },
    },
]

WINDOWS_PROFILES: list[dict] = [
    {
        "id": "retroarch",
        "name": "RetroArch",
        "emulator": "retroarch",
        "variant": "windows",
        "kinds": {
            "saves": ["AppData/Roaming/RetroArch/saves"],
            "states": ["AppData/Roaming/RetroArch/states"],
        },
    },
    {
        "id": "pcsx2",
        "name": "PCSX2",
        "emulator": "pcsx2",
        "variant": "windows",
        "kinds": {
            "memcards": [
                "Documents/PCSX2/memcards",
                "AppData/Roaming/PCSX2/memcards",
            ],
            "sstates": [
                "Documents/PCSX2/sstates",
                "AppData/Roaming/PCSX2/sstates",
            ],
        },
    },
    {
        "id": "dolphin",
        "name": "Dolphin",
        "emulator": "dolphin",
        "variant": "windows",
        "kinds": {
            "GC": ["Documents/Dolphin Emulator/GC"],
            "Wii": ["Documents/Dolphin Emulator/Wii"],
        },
    },
]


@dataclass(frozen=True)
class UserDirs:
    root: Path
    platform: PlatformName
    config_dir: Path
    data_dir: Path
    backup_dir: Path
    state_path: Path
    cache_dir: Path


def detect_platform(explicit: str | None = None) -> PlatformName:
    name = (explicit or os.environ.get("RETRO_SAVE_SYNC_PLATFORM") or sys.platform).lower()
    if name.startswith("win"):
        return "windows"
    return "linux"


def default_user_root(platform: PlatformName | None = None) -> Path:
    platform = platform or detect_platform()
    override = os.environ.get("RETRO_SAVE_SYNC_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if platform == "windows":
        return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())
    return Path(os.environ.get("HOME") or Path.home())


def user_dirs(
    root: Path | None = None,
    platform: PlatformName | None = None,
    backup_root: Path | None = None,
) -> UserDirs:
    platform = platform or detect_platform()
    root = Path(root) if root is not None else default_user_root(platform)
    root = root.expanduser().resolve()
    if platform == "windows":
        config_dir = root / "AppData" / "Roaming" / "retro-save-sync"
        data_dir = root / "AppData" / "Local" / "retro-save-sync"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        xdg_data = os.environ.get("XDG_DATA_HOME")
        # When a test root is in play, always stay inside that root.
        env_root = os.environ.get("RETRO_SAVE_SYNC_ROOT")
        if env_root or root != Path.home():
            config_dir = root / ".config" / "retro-save-sync"
            data_dir = root / ".local" / "share" / "retro-save-sync"
        else:
            config_dir = Path(xdg_config) / "retro-save-sync" if xdg_config else root / ".config" / "retro-save-sync"
            data_dir = Path(xdg_data) / "retro-save-sync" if xdg_data else root / ".local" / "share" / "retro-save-sync"
    backup_dir = Path(backup_root).expanduser().resolve() if backup_root else data_dir / "backups"
    return UserDirs(
        root=root,
        platform=platform,
        config_dir=config_dir,
        data_dir=data_dir,
        backup_dir=backup_dir,
        state_path=data_dir / "state.json",
        cache_dir=data_dir / "cache",
    )


def builtin_specs(platform: PlatformName) -> list[dict]:
    return WINDOWS_PROFILES if platform == "windows" else LINUX_PROFILES


def resolve_kind_paths(root: Path, candidates: Iterable[str]) -> list[Path]:
    existing: list[Path] = []
    for rel in candidates:
        path = (root / rel).resolve()
        if path.is_dir() and path not in existing:
            existing.append(path)
    return existing


def preferred_kind_path(root: Path, candidates: Iterable[str]) -> Path:
    existing = resolve_kind_paths(root, candidates)
    if existing:
        return existing[0]
    first = next(iter(candidates))
    return (root / first).resolve()


def roots_for_spec(root: Path, spec: dict) -> list[SaveRoot]:
    roots: list[SaveRoot] = []
    for kind, candidates in spec["kinds"].items():
        existing = resolve_kind_paths(root, candidates)
        if existing:
            for path in existing:
                roots.append(SaveRoot(kind=kind, path=path))
        else:
            roots.append(SaveRoot(kind=kind, path=preferred_kind_path(root, candidates)))
    return roots

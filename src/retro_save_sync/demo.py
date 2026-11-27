"""Seed a hermetic demo/test fixture with original dummy save files only.

Never writes copyrighted games, ROMs, or BIOS. Every dummy file starts with
the ASCII banner `VETTV-DUMMY-SAVE` plus original placeholder names.
"""

from __future__ import annotations

import json
from pathlib import Path

from retro_save_sync.config import AppConfig, load_config
from retro_save_sync.engine import apply_plan, preview
from retro_save_sync.paths import user_dirs
from retro_save_sync.util import ensure_dir

BANNER = b"VETTV-DUMMY-SAVE\nOriginal VetTV placeholder. Not a real game file.\n"


def write_dummy(path: Path, payload: bytes, size: int | None = None) -> Path:
    ensure_dir(path.parent)
    body = BANNER + payload
    if size is not None and size > len(body):
        body = body + bytes((i * 17 + 31) % 256 for i in range(size - len(body)))
    path.write_bytes(body)
    return path


def seed_emulator_tree(root: Path, platform: str = "linux") -> dict[str, Path]:
    """Create native RetroArch / PCSX2 / Dolphin / custom folders plus dummy saves."""
    root = Path(root)
    if platform == "windows":
        paths = {
            "ra_saves": root / "AppData/Roaming/RetroArch/saves",
            "ra_states": root / "AppData/Roaming/RetroArch/states",
            "ps2_mem": root / "Documents/PCSX2/memcards",
            "ps2_ss": root / "Documents/PCSX2/sstates",
            "gc": root / "Documents/Dolphin Emulator/GC",
            "wii": root / "Documents/Dolphin Emulator/Wii",
        }
    else:
        paths = {
            "ra_saves": root / ".config/retroarch/saves",
            "ra_states": root / ".config/retroarch/states",
            "ps2_mem": root / ".config/PCSX2/memcards",
            "ps2_ss": root / ".config/PCSX2/sstates",
            "gc": root / ".local/share/dolphin-emu/GC",
            "wii": root / ".local/share/dolphin-emu/Wii",
        }
    custom = root / "Games" / "NonSteam" / "saves"
    paths["custom"] = custom
    for folder in paths.values():
        ensure_dir(folder)

    write_dummy(paths["ra_saves"] / "Neon Circuit.srm", b"neon-circuit-slot-a\n", size=2048)
    write_dummy(paths["ra_saves"] / "Penguin Quest.srm", b"penguin-quest-100\n", size=2048)
    write_dummy(paths["ra_states"] / "Starlight Express.state", b"starlight-midrun\n", size=4096)
    write_dummy(paths["ps2_mem"] / "Memory Card A.ps2", b"vettv-arena-memcard-a\n", size=8192)
    write_dummy(paths["ps2_mem"] / "Memory Card B.ps2", b"vettv-arena-memcard-b\n", size=8192)
    write_dummy(paths["ps2_ss"] / "Wave Rider.p2s", b"wave-rider-state\n", size=2048)
    write_dummy(paths["gc"] / "Sky Harbor.gci", b"sky-harbor-gc\n", size=1024)
    write_dummy(paths["wii"] / "title" / "Harbor Run.sav", b"harbor-run-wii\n", size=1024)
    write_dummy(custom / "Pulse Kart.sav", b"pulse-kart-custom\n", size=512)
    return paths


def write_demo_config(root: Path, target: Path, platform: str = "linux") -> Path:
    dirs = user_dirs(root=root, platform=platform)  # type: ignore[arg-type]
    ensure_dir(dirs.config_dir)
    custom = root / "Games" / "NonSteam" / "saves"
    data = {
        "root_override": str(root),
        "platform": platform,
        "backup_root": str(dirs.backup_dir),
        "custom_profiles": [
            {
                "id": "nonsteam-pulse",
                "name": "Non-Steam: Pulse Kart",
                "paths": {"saves": str(custom)},
            }
        ],
        "target": {"type": "folder", "path": str(target)},
    }
    path = dirs.config_dir / "config.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def seed_demo_with_history(root: Path, *, platform: str = "linux") -> AppConfig:
    """Populate saves, a folder target, one overwrite backup, and one conflict."""
    root = Path(root)
    target = root / "SyncTarget"
    ensure_dir(target)
    seed_emulator_tree(root, platform=platform)
    config_path = write_demo_config(root, target, platform=platform)
    cfg = load_config(config_path=config_path, root=root, platform=platform)

    # First sync: seed the target with the current local files (no overwrites).
    apply_plan(cfg, dry_run=False)

    # Change one local file so a later sync will overwrite the target copy
    # (needs a last-sync hash, which the first sync just wrote).
    ra = (
        root / "AppData/Roaming/RetroArch/saves/Neon Circuit.srm"
        if platform == "windows"
        else root / ".config/retroarch/saves/Neon Circuit.srm"
    )
    write_dummy(ra, b"neon-circuit-slot-a-UPDATED\n", size=2048)
    apply_plan(cfg, dry_run=False)

    # Create a true conflict: change both sides independently.
    penguin = (
        root / "AppData/Roaming/RetroArch/saves/Penguin Quest.srm"
        if platform == "windows"
        else root / ".config/retroarch/saves/Penguin Quest.srm"
    )
    remote_penguin = target / "retroarch" / "saves" / "Penguin Quest.srm"
    write_dummy(penguin, b"penguin-quest-local-edit\n", size=2048)
    write_dummy(remote_penguin, b"penguin-quest-remote-edit\n", size=2048)
    # Leave the conflict in place for the GUI / preview to show.
    preview(cfg)
    return cfg


def maybe_seed(root: Path, platform: str = "linux") -> AppConfig | None:
    marker = Path(root) / ".config" / "retro-save-sync" / "config.json"
    if platform == "windows":
        marker = Path(root) / "AppData" / "Roaming" / "retro-save-sync" / "config.json"
    if marker.is_file():
        return load_config(config_path=marker, root=root, platform=platform)
    return seed_demo_with_history(root, platform=platform)

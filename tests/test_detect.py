from __future__ import annotations

from pathlib import Path

from retro_save_sync.detect import detect_custom, detect_profiles
from retro_save_sync.demo import seed_emulator_tree, write_dummy
from retro_save_sync.paths import preferred_kind_path, user_dirs


def test_linux_native_and_flatpak_paths(linux_root: Path):
    # Also create Flatpak trees so both variants are "present".
    fp_ra = linux_root / ".var/app/org.libretro.RetroArch/config/retroarch/saves"
    fp_ps2 = linux_root / ".var/app/net.pcsx2.PCSX2/config/PCSX2/memcards"
    fp_dol = linux_root / ".var/app/org.dolphin_emu.dolphin-emu/data/dolphin-emu/GC"
    write_dummy(fp_ra / "Flatpak Neon.srm", b"flatpak-ra\n", size=256)
    write_dummy(fp_ps2 / "Flatpak Card.ps2", b"flatpak-ps2\n", size=256)
    write_dummy(fp_dol / "Flatpak Harbor.gci", b"flatpak-gc\n", size=256)
    # States / Wii dirs should also exist for a complete present profile.
    (linux_root / ".var/app/org.libretro.RetroArch/config/retroarch/states").mkdir(parents=True)
    (linux_root / ".var/app/net.pcsx2.PCSX2/config/PCSX2/sstates").mkdir(parents=True)
    (linux_root / ".var/app/org.dolphin_emu.dolphin-emu/data/dolphin-emu/Wii").mkdir(parents=True)

    profiles = {p.id: p for p in detect_profiles(linux_root, "linux")}
    assert profiles["retroarch"].present
    assert any(r.kind == "saves" and r.path.name == "saves" for r in profiles["retroarch"].roots)
    assert linux_root / ".config/retroarch/saves" in [r.path for r in profiles["retroarch"].roots]
    assert profiles["retroarch"].file_count >= 2

    assert profiles["pcsx2"].present
    assert any(r.path == linux_root / ".config/PCSX2/memcards" for r in profiles["pcsx2"].roots)

    assert profiles["dolphin"].present
    assert any(r.path == linux_root / ".local/share/dolphin-emu/GC" for r in profiles["dolphin"].roots)
    assert any(r.path == linux_root / ".local/share/dolphin-emu/Wii" for r in profiles["dolphin"].roots)

    assert profiles["retroarch-flatpak"].present
    assert any("org.libretro.RetroArch" in str(r.path) for r in profiles["retroarch-flatpak"].roots)
    assert profiles["pcsx2-flatpak"].present
    assert any("net.pcsx2.PCSX2" in str(r.path) for r in profiles["pcsx2-flatpak"].roots)
    assert profiles["dolphin-flatpak"].present
    assert any("org.dolphin_emu.dolphin-emu" in str(r.path) for r in profiles["dolphin-flatpak"].roots)


def test_windows_appdata_and_documents_paths(windows_root: Path):
    profiles = {p.id: p for p in detect_profiles(windows_root, "windows")}
    assert set(profiles) == {"retroarch", "pcsx2", "dolphin"}
    assert profiles["retroarch"].present
    assert any(
        r.path == windows_root / "AppData/Roaming/RetroArch/saves" for r in profiles["retroarch"].roots
    )
    assert profiles["pcsx2"].present
    assert any(r.path == windows_root / "Documents/PCSX2/memcards" for r in profiles["pcsx2"].roots)
    assert profiles["dolphin"].present
    assert any(r.path == windows_root / "Documents/Dolphin Emulator/GC" for r in profiles["dolphin"].roots)


def test_custom_non_steam_profile(linux_root: Path):
    custom_dir = linux_root / "Games" / "NonSteam" / "saves"
    profiles = detect_custom(
        [{"id": "nonsteam-pulse", "name": "Non-Steam: Pulse Kart", "paths": {"saves": str(custom_dir)}}]
    )
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.id == "custom-nonsteam-pulse"
    assert profile.emulator == "custom"
    assert profile.present
    assert profile.file_count == 1
    assert profile.roots[0].path == custom_dir.resolve()


def test_missing_profiles_are_reported_with_preferred_paths(tmp_path: Path):
    root = tmp_path / "empty-home"
    root.mkdir()
    profiles = detect_profiles(root, "linux", include_missing=True)
    ra = next(p for p in profiles if p.id == "retroarch")
    assert ra.present is False
    assert ra.file_count == 0
    saves = next(r for r in ra.roots if r.kind == "saves")
    assert saves.path == (root / ".config/retroarch/saves").resolve()


def test_user_dirs_honor_root_override(tmp_path: Path):
    root = tmp_path / "home"
    dirs = user_dirs(root=root, platform="linux")
    assert dirs.config_dir == (root / ".config/retro-save-sync").resolve()
    assert dirs.backup_dir == (root / ".local/share/retro-save-sync/backups").resolve()
    win = user_dirs(root=root, platform="windows")
    assert win.config_dir == (root / "AppData/Roaming/retro-save-sync").resolve()


def test_preferred_path_picks_first_existing(tmp_path: Path):
    a = tmp_path / "a" / "memcards"
    b = tmp_path / "b" / "memcards"
    b.mkdir(parents=True)
    chosen = preferred_kind_path(tmp_path, ["a/memcards", "b/memcards"])
    assert chosen == b.resolve()
    # If none exist, first candidate is the preferred default.
    empty = tmp_path / "empty"
    empty.mkdir()
    preferred = preferred_kind_path(empty, ["x/memcards", "y/memcards"])
    assert preferred == (empty / "x/memcards").resolve()

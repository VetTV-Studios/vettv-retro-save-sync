# Retro Save Sync — v1 Plan

VetTV Studios tool for safe, reversible sync of emulator saves across Linux, SteamOS, and Windows. v1 is a local prototype only: no GitHub repo, no public release, no spend.

## Stack

- **Python 3.11+ standard library** for the core, CLI, and tests (pathlib, hashlib, json, subprocess, argparse, dataclasses).
- **PySide6 / Qt 6** for the dark VetTV desktop GUI (Essentials only: QtCore, QtGui, QtWidgets). Already matches the box’s Qt 6.8 libraries.
- **pytest** for the automated suite.
- **git CLI** for the git target (already present on Linux/macOS; Git for Windows on that side).
- **rclone CLI** (optional adapter): invoked when installed, otherwise reported as unavailable. Folder and git targets keep working.
- **Packaging (v1 spec only, not executed here):** PyInstaller onefile → Linux AppImage wrapper + Windows `.exe` via GitHub Actions. See `packaging/github-actions-build.yml`.

Why this stack: tiny core footprint, no service or cloud spend, one codebase for CLI + GUI, and a GUI toolkit that already ships on SteamOS Desktop and Windows.

## Architecture

```
scan (detect) ──► index local files (SHA-256 + mtime_ns)
                      │
preview / sync ──► index target (folder | git work tree | rclone staging)
                      │
              three-way classify vs last-sync state
                      │
         push / pull / conflict / skip
                      │
         before any overwrite: timestamped rollback backup
                      │
         apply copies ──► update state.json
                      │
         git: add / commit / push     rclone: copy staging → remote
```

Layout (never store docs or screenshots in `dist/` or `build/`):

- `src/retro_save_sync/` — library, CLI (`cli.py`), GUI (`gui.py`)
- `tests/` — pytest suite
- `screenshots/` — verified GUI captures
- `packaging/` — PyInstaller spec + Actions workflow template
- Config: `<root>/.config/retro-save-sync/config.json` (Linux/SteamOS) or `%APPDATA%\retro-save-sync\config.json` (Windows)
- State + backups: `<data>/state.json` and `<data>/backups/<YYYYMMDD-HHMMSS>/<profile>/...` plus `manifest.json`

`RETRO_SAVE_SYNC_ROOT` / `--root` overrides the user home so tests and demos never touch a real profile. `RETRO_SAVE_SYNC_PLATFORM=windows|linux` selects the path map.

### Auto-detection (v1)

| Emulator  | Linux / SteamOS native              | Flatpak                                      | Windows                                      |
|-----------|-------------------------------------|----------------------------------------------|----------------------------------------------|
| RetroArch | `~/.config/retroarch/{saves,states}` | `org.libretro.RetroArch` under `~/.var/app` | `%APPDATA%\RetroArch\{saves,states}`         |
| PCSX2     | `~/.config/PCSX2/{memcards,sstates}` (then share / Documents) | `net.pcsx2.PCSX2`                    | `%USERPROFILE%\Documents\PCSX2\...`          |
| Dolphin   | `~/.local/share/dolphin-emu/{GC,Wii}` | `org.dolphin_emu.dolphin-emu`              | `%USERPROFILE%\Documents\Dolphin Emulator\...` |
| Custom    | User-named profiles with arbitrary paths (non-Steam)        | —                          | same                                         |

### Sync targets

- **Folder** (v1, end-to-end): any local or mounted path (USB, NAS, Drive/OneDrive mount).
- **Git** (v1, end-to-end): work tree or local bare repo via `git` CLI. Engine owns file conflicts; git is used to commit and push after a safe apply, and to fetch before preview.
- **rclone** (v1 adapter): `rclone copy` with `--dry-run` and destination safety checks. If `rclone` is missing, the app says so and keeps folder/git working. Staging under the data cache lets the same SHA-256 planner run.

### Safety

- Same path, same SHA-256 → skip.
- Only on one side → push or pull.
- Both sides differ: three-way vs last-sync hash. Only one side changed → that side wins (and the overwritten file is snapshotted first). Both changed, or no last-sync hash → **conflict**, never overwritten.
- Before every overwrite: `backups/<YYYYMMDD-HHMMSS>/<profile>/...` + JSON manifest. `restore` copies the snapshot back and verifies SHA-256.

## v1 scope (this prototype)

- Detection, folder sync, git sync, rclone adapter, dry-run preview, automatic rollback backups, CLI (`scan | preview | sync | backups | restore`), dark VetTV GUI, pytest coverage of all of the above, packaging workflow *spec*.
- Dummy `.srm` / `.ps2` / `.gci` fixtures only (banner `VETTV-DUMMY-SAVE`). No games, ROMs, or BIOS.

## v2 roadmap

- Parse `retroarch.cfg` / PCSX2 and Dolphin INI for non-default save directories.
- Optional encrypted folder target and Watch-and-sync (debounce + same conflict rules).
- Per-conflict chooser in the GUI (“keep local / keep target / keep both”).
- Cloud rclone remotes documented with a first-run token flow (still $0, user-owned remotes).
- SteamOS Game Mode plugin / Decky glance (Desktop app stays the source of truth).
- Signed AppImage + Windows installer once Vet approves a public repo.

## Linux + Windows GitHub Actions packaging plan

Not run in this prototype (no repo, no push, no release). The template lives at `packaging/github-actions-build.yml` and the PyInstaller spec at `packaging/retro-save-sync.spec`.

1. When Vet approves a repo, copy the workflow to `.github/workflows/build.yml`.
2. `ubuntu-latest`: install Qt deps if needed, `pip install pyinstaller PySide6-Essentials`, `pyinstaller packaging/retro-save-sync.spec`, wrap the onefile binary with `appimagetool` into `RetroSaveSync-x86_64.AppImage`.
3. `windows-latest`: same spec → `RetroSaveSync.exe`.
4. Publish artifacts only (no auto GitHub Release until Vet says so).
5. Keep docs and screenshots in `screenshots/` and `PLAN.md`, never inside `dist/` or `build/`.

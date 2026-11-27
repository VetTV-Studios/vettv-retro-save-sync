# PyInstaller spec for Retro Save Sync (Linux AppImage input + Windows .exe).
# Run from the repo root:
#   pyinstaller packaging/retro-save-sync.spec
# Do not treat dist/ or build/ as a place to keep docs or screenshots.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
project = Path(SPECPATH).resolve().parent
src = project / "src"

datas = []
binaries = []
hiddenimports = ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

try:
    d, b, h = collect_all("PySide6")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

a = Analysis(
    [str(src / "retro_save_sync" / "__main__.py")],
    pathex=[str(src)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RetroSaveSync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False if sys.platform.startswith("win") else True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

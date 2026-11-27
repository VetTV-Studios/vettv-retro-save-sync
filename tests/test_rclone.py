from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest

from retro_save_sync.config import SyncTarget
from retro_save_sync.demo import write_dummy
from retro_save_sync.targets import (
    RcloneTargetError,
    rclone_available,
    rclone_dry_run,
    rclone_push_staging,
    rclone_status,
    _validate_rclone_spec,
)


def test_rclone_gracefully_detected_when_absent(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    # shutil.which may still find rclone if PATH is the only search — also
    # hide it by clearing PATH completely.
    monkeypatch.setenv("PATH", "")
    assert rclone_available() is False
    status = rclone_status()
    assert status["available"] is False
    assert "not installed" in status["message"]


def test_rclone_adapter_dry_run_and_copy_with_fake_binary(tmp_path: Path, linux_cfg, monkeypatch):
    log = tmp_path / "rclone.log"
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    script = fake / "rclone"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            echo "$0 $@" >> "{log}"
            # emulate: rclone copy SRC DEST
            cmd="$1"; shift
            if [ "$cmd" = "version" ]; then
              echo "rclone v1.0.0-fake"
              exit 0
            fi
            if [ "$cmd" != "copy" ]; then
              echo "unexpected $cmd" >&2
              exit 2
            fi
            src="$1"; dest="$2"; shift 2
            dry=0
            for a in "$@"; do
              [ "$a" = "--dry-run" ] && dry=1
            done
            if [ "$dry" = "1" ]; then
              echo "DRY RUN $src -> $dest"
              exit 0
            fi
            mkdir -p "$dest"
            cp -a "$src/." "$dest/" 2>/dev/null || cp -a "$src" "$dest"
            exit 0
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ.get('PATH', '')}")
    assert rclone_available() is True
    assert "fake" in rclone_status()["version"]

    src = tmp_path / "staging"
    src.mkdir()
    write_dummy(src / "retroarch/saves/Neon Circuit.srm", b"via-rclone\n", size=128)
    dry = rclone_dry_run(str(src), str(remote_dir))
    assert dry["ok"] is True
    assert "--dry-run" in dry["cmd"]
    assert list(remote_dir.rglob("*.srm")) == []
    assert "DRY RUN" in dry["stdout"]

    target = SyncTarget(type="rclone", path="", remote=str(remote_dir))
    pushed = rclone_push_staging(linux_cfg, target, src, dry_run=False)
    assert pushed["ok"] is True
    copied = remote_dir / "retroarch/saves/Neon Circuit.srm"
    assert copied.is_file()
    log_text = log.read_text()
    assert "copy" in log_text
    assert "--dry-run" in log_text


def test_rclone_refuses_unsafe_destinations():
    with pytest.raises(RcloneTargetError):
        _validate_rclone_spec("/")
    with pytest.raises(RcloneTargetError):
        _validate_rclone_spec("--dangerous")
    with pytest.raises(RcloneTargetError):
        _validate_rclone_spec("")
    assert _validate_rclone_spec("gdrive:vettv-saves") == "gdrive:vettv-saves"

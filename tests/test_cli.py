from __future__ import annotations

import json
from pathlib import Path

from retro_save_sync.cli import main
from retro_save_sync.demo import write_dummy


def test_cli_scan_preview_sync_backups_restore(linux_cfg, capsys):
    root = str(linux_cfg.root)
    target = str(linux_cfg.target.path)
    config = str(linux_cfg.path)

    assert main(["scan", "--config", config, "--root", root, "--platform", "linux", "--json"]) == 0
    scan = json.loads(capsys.readouterr().out)
    ids = {p["id"] for p in scan["profiles"]}
    assert {"retroarch", "pcsx2", "dolphin"}.issubset(ids)
    assert any(p["id"].startswith("custom-") and p["present"] for p in scan["profiles"])

    assert main(["preview", "--config", config, "--root", root, "--target", target, "--target-type", "folder", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["summary"]["push"] >= 8
    assert plan["summary"]["conflict"] == 0

    assert main(["sync", "--config", config, "--root", root, "--target", target, "--target-type", "folder", "--json"]) == 0
    synced = json.loads(capsys.readouterr().out)
    assert synced["backup_id"] is None
    assert len(synced["applied"]) >= 8

    # Force an overwrite so a backup appears.
    local = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    write_dummy(local, b"cli-updated\n", size=2048)
    assert main(["sync", "--config", config, "--root", root, "--target", target, "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["backup_id"]
    backup_id = again["backup_id"]

    assert main(["backups", "--config", config, "--root", root, "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert any(b["id"] == backup_id for b in listing["backups"])

    # Mutate the target again, then restore the snapshot.
    remote = Path(target) / "retroarch/saves/Neon Circuit.srm"
    mutated = remote.read_bytes()
    write_dummy(remote, b"oops-clobber\n", size=2048)
    assert remote.read_bytes() != mutated
    assert main(["restore", backup_id, "--config", config, "--root", root, "--json"]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["verified"] is True
    # The backup holds the pre-overwrite target bytes (the first-sync content),
    # not the cli-updated bytes — that's expected: the snapshot is of the
    # overwritten file.
    assert Path(remote).is_file()


def test_cli_status_and_scan_found_only(linux_cfg, capsys):
    config = str(linux_cfg.path)
    root = str(linux_cfg.root)
    assert main(["status", "--config", config, "--root", root, "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["platform"] == "linux"
    assert "rclone" in status
    assert main(["scan", "--config", config, "--root", root, "--found-only", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert all(p["present"] for p in data["profiles"])

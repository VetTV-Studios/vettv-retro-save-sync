from __future__ import annotations

from pathlib import Path

from retro_save_sync.demo import write_dummy
from retro_save_sync.engine import apply_plan, preview
from retro_save_sync.util import sha256_file


def test_folder_sync_push_new_files(linux_cfg):
    plan = preview(linux_cfg)
    assert plan.conflicts == []
    assert plan.pulls == []
    assert len(plan.pushes) >= 8
    assert all(not item.will_overwrite for item in plan.pushes)

    result = apply_plan(linux_cfg, plan, dry_run=False)
    assert result.backup is None
    assert len(result.applied) == len(plan.pushes)

    target = Path(linux_cfg.target.path)
    local_neon = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    remote_neon = target / "retroarch/saves/Neon Circuit.srm"
    assert remote_neon.is_file()
    assert sha256_file(remote_neon) == sha256_file(local_neon)

    # Second preview: everything identical, all skips.
    again = preview(linux_cfg)
    assert again.summary()["push"] == 0
    assert again.summary()["pull"] == 0
    assert again.summary()["conflict"] == 0
    assert again.summary()["skip"] >= 8


def test_folder_sync_pulls_target_only_file(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    incoming = Path(linux_cfg.target.path) / "retroarch/saves/Incoming Demo.srm"
    write_dummy(incoming, b"from-the-target\n", size=256)

    plan = preview(linux_cfg)
    pulls = [i for i in plan.pulls if i.relpath.endswith("Incoming Demo.srm")]
    assert len(pulls) == 1
    assert pulls[0].will_overwrite is False

    apply_plan(linux_cfg, plan, dry_run=False)
    dest = linux_cfg.root / ".config/retroarch/saves/Incoming Demo.srm"
    assert dest.is_file()
    assert sha256_file(dest) == sha256_file(incoming)


def test_dry_run_does_not_write(linux_cfg):
    plan = preview(linux_cfg)
    result = apply_plan(linux_cfg, plan, dry_run=True)
    assert result.dry_run is True
    assert result.applied == []
    target = Path(linux_cfg.target.path)
    assert list(target.rglob("*.srm")) == []

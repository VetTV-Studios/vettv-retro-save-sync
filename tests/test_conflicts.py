from __future__ import annotations

from pathlib import Path

from retro_save_sync.demo import write_dummy
from retro_save_sync.engine import apply_plan, load_state, preview
from retro_save_sync.util import sha256_file


def test_differing_hashes_without_last_sync_are_conflicts(linux_cfg):
    target = Path(linux_cfg.target.path)
    local = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    remote = target / "retroarch/saves/Neon Circuit.srm"
    write_dummy(remote, b"different-remote-bytes\n", size=2048)
    assert sha256_file(local) != sha256_file(remote)

    plan = preview(linux_cfg)
    neon = next(i for i in plan.items if i.relpath.endswith("Neon Circuit.srm"))
    assert neon.action == "conflict"
    assert neon.will_overwrite is False

    before = sha256_file(local), sha256_file(remote)
    result = apply_plan(linux_cfg, plan, dry_run=False)
    assert neon.key in {i.key for i in result.skipped_conflicts}
    assert (sha256_file(local), sha256_file(remote)) == before


def test_three_way_push_when_only_local_changed(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    local = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    remote = Path(linux_cfg.target.path) / "retroarch/saves/Neon Circuit.srm"
    old_remote = sha256_file(remote)
    write_dummy(local, b"local-only-update\n", size=2048)

    plan = preview(linux_cfg)
    neon = next(i for i in plan.items if i.relpath.endswith("Neon Circuit.srm"))
    assert neon.action == "push"
    assert neon.will_overwrite is True

    apply_plan(linux_cfg, plan, dry_run=False)
    assert sha256_file(remote) == sha256_file(local)
    assert sha256_file(remote) != old_remote


def test_three_way_pull_when_only_target_changed(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    local = linux_cfg.root / ".config/retroarch/saves/Penguin Quest.srm"
    remote = Path(linux_cfg.target.path) / "retroarch/saves/Penguin Quest.srm"
    write_dummy(remote, b"remote-only-update\n", size=2048)

    plan = preview(linux_cfg)
    item = next(i for i in plan.items if i.relpath.endswith("Penguin Quest.srm"))
    assert item.action == "pull"
    assert item.will_overwrite is True
    apply_plan(linux_cfg, plan, dry_run=False)
    assert sha256_file(local) == sha256_file(remote)


def test_both_changed_since_last_sync_is_conflict(linux_cfg):
    apply_plan(linux_cfg, dry_run=False)
    local = linux_cfg.root / ".config/retroarch/saves/Penguin Quest.srm"
    remote = Path(linux_cfg.target.path) / "retroarch/saves/Penguin Quest.srm"
    write_dummy(local, b"local-edit\n", size=2048)
    write_dummy(remote, b"remote-edit\n", size=2048)
    plan = preview(linux_cfg)
    item = next(i for i in plan.items if i.relpath.endswith("Penguin Quest.srm"))
    assert item.action == "conflict"
    before = sha256_file(local), sha256_file(remote)
    apply_plan(linux_cfg, plan, dry_run=False)
    assert (sha256_file(local), sha256_file(remote)) == before
    # Last-sync hash must still be the pre-conflict value, not either side.
    state = load_state(linux_cfg.dirs.state_path)
    last = state["files"][item.key]["sha256"]
    assert last not in {before[0], before[1]}

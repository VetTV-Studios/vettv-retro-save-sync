from __future__ import annotations

import subprocess
from pathlib import Path

from retro_save_sync.demo import write_dummy
from retro_save_sync.engine import apply_plan, preview
from retro_save_sync.util import sha256_file


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-c", "user.name=Test", "-c", "user.email=test@vettv.local", *args]
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=True)


def test_git_sync_to_bare_remote_roundtrip(linux_cfg, tmp_path: Path):
    bare = tmp_path / "saves.git"
    _git(["init", "--bare", "-b", "main", str(bare)])
    linux_cfg.target.type = "git"
    linux_cfg.target.path = str(bare)
    linux_cfg.target.git_remote = "origin"

    plan = preview(linux_cfg)
    assert plan.target_type == "git"
    assert any(i.action == "push" for i in plan.items)

    result = apply_plan(linux_cfg, dry_run=False)
    assert result.git is not None
    assert result.git.get("committed") is True
    assert result.git.get("pushed") is True

    # A fresh clone of the bare repo must contain the pushed save files.
    clone = tmp_path / "clone"
    _git(["clone", str(bare), str(clone)])
    remote_file = clone / "retroarch/saves/Neon Circuit.srm"
    local_file = linux_cfg.root / ".config/retroarch/saves/Neon Circuit.srm"
    assert remote_file.is_file()
    assert sha256_file(remote_file) == sha256_file(local_file)

    # A second machine-style change: commit a new file on the bare remote via a
    # second clone, then sync should pull it into the local RetroArch folder.
    donor = tmp_path / "donor"
    _git(["clone", str(bare), str(donor)])
    incoming = donor / "retroarch/saves/From Git.srm"
    write_dummy(incoming, b"arrived-via-git\n", size=256)
    _git(["add", "-A"], cwd=donor)
    _git(["commit", "-m", "add incoming save"], cwd=donor)
    _git(["push", "origin", "HEAD"], cwd=donor)

    plan2 = preview(linux_cfg)
    pulls = [i for i in plan2.pulls if i.relpath.endswith("From Git.srm")]
    assert len(pulls) == 1
    apply_plan(linux_cfg, plan2, dry_run=False)
    dest = linux_cfg.root / ".config/retroarch/saves/From Git.srm"
    assert dest.is_file()
    assert sha256_file(dest) == sha256_file(incoming)


def test_git_worktree_target_inits_if_needed(linux_cfg, tmp_path: Path):
    work = tmp_path / "worktree"
    linux_cfg.target.type = "git"
    linux_cfg.target.path = str(work)
    result = apply_plan(linux_cfg, dry_run=False)
    assert (work / ".git").exists() or (work / ".git").is_file()
    assert (work / "retroarch/saves/Neon Circuit.srm").is_file()
    log = _git(["log", "-1", "--pretty=%s"], cwd=work)
    assert "retro-save-sync" in log.stdout
    assert result.git and result.git.get("committed") is True

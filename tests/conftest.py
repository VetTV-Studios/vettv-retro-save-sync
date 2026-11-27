from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from retro_save_sync.config import load_config
from retro_save_sync.demo import seed_emulator_tree, write_demo_config, write_dummy
from retro_save_sync.paths import user_dirs


@pytest.fixture
def linux_root(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    seed_emulator_tree(root, platform="linux")
    return root


@pytest.fixture
def windows_root(tmp_path: Path) -> Path:
    root = tmp_path / "Users" / "Vet"
    seed_emulator_tree(root, platform="windows")
    return root


@pytest.fixture
def linux_cfg(linux_root: Path, tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    path = write_demo_config(linux_root, target, platform="linux")
    return load_config(config_path=path, root=linux_root, platform="linux")


@pytest.fixture
def env_root(linux_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("RETRO_SAVE_SYNC_ROOT", str(linux_root))
    monkeypatch.setenv("RETRO_SAVE_SYNC_PLATFORM", "linux")
    return linux_root

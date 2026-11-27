from __future__ import annotations

from pathlib import Path

from retro_save_sync.models import PlatformName, Profile, SaveRoot
from retro_save_sync.paths import builtin_specs, roots_for_spec
from retro_save_sync.util import format_bytes, iter_files


def _count_files(profile: Profile) -> None:
    total = 0
    bytes_ = 0
    seen: set[Path] = set()
    if not profile.present:
        profile.file_count = 0
        profile.total_bytes = 0
        return
    for root in profile.roots:
        if not root.path.is_dir():
            continue
        for path in iter_files(root.path):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            total += 1
            bytes_ += path.stat().st_size
    profile.file_count = total
    profile.total_bytes = bytes_


def detect_builtin(root: Path, platform: PlatformName) -> list[Profile]:
    profiles: list[Profile] = []
    for spec in builtin_specs(platform):
        roots = roots_for_spec(root, spec)
        present = any(r.path.is_dir() for r in roots)
        profile = Profile(
            id=spec["id"],
            name=spec["name"],
            emulator=spec["emulator"],
            variant=spec["variant"],
            roots=roots,
            present=present,
        )
        _count_files(profile)
        profiles.append(profile)
    return profiles


def detect_custom(custom_profiles: list[dict]) -> list[Profile]:
    profiles: list[Profile] = []
    for index, entry in enumerate(custom_profiles or []):
        name = str(entry.get("name") or f"Custom {index + 1}").strip()
        pid = str(entry.get("id") or _slug(name))
        paths = entry.get("paths") or {}
        roots: list[SaveRoot] = []
        if entry.get("path") and not paths:
            paths = {"saves": entry["path"]}
        for kind, raw in paths.items():
            path = Path(raw).expanduser().resolve()
            roots.append(SaveRoot(kind=str(kind), path=path))
        present = any(r.path.is_dir() for r in roots)
        profile = Profile(
            id=f"custom-{pid}",
            name=name,
            emulator="custom",
            variant="custom",
            roots=roots,
            present=present,
        )
        _count_files(profile)
        profiles.append(profile)
    return profiles


def detect_profiles(
    root: Path,
    platform: PlatformName,
    custom_profiles: list[dict] | None = None,
    include_missing: bool = True,
) -> list[Profile]:
    profiles = detect_builtin(root, platform)
    profiles.extend(detect_custom(custom_profiles or []))
    if not include_missing:
        profiles = [p for p in profiles if p.present]
    return profiles


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "profile"


def format_profile_line(profile: Profile) -> str:
    status = "found" if profile.present else "missing"
    size = format_bytes(profile.total_bytes) if profile.present else "-"
    roots = ", ".join(f"{r.kind}={r.path}" for r in profile.roots)
    return (
        f"{profile.id:22}  {profile.name:24}  {status:7}  "
        f"{profile.file_count:4} files  {size:>8}  {roots}"
    )

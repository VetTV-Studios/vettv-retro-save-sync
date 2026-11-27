from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

PlatformName = Literal["linux", "windows"]
TargetType = Literal["folder", "git", "rclone"]
ActionName = Literal["push", "pull", "conflict", "skip"]


@dataclass(frozen=True)
class SaveRoot:
    kind: str
    path: Path


@dataclass
class Profile:
    id: str
    name: str
    emulator: str
    variant: str
    roots: list[SaveRoot] = field(default_factory=list)
    present: bool = False
    file_count: int = 0
    total_bytes: int = 0

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "emulator": self.emulator,
            "variant": self.variant,
            "present": self.present,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "roots": [{"kind": r.kind, "path": str(r.path)} for r in self.roots],
        }


@dataclass
class FileRecord:
    profile_id: str
    kind: str
    relpath: str
    path: Path
    sha256: str
    mtime_ns: int
    size: int

    @property
    def key(self) -> str:
        return f"{self.profile_id}/{self.kind}/{self.relpath}"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["key"] = self.key
        return data


@dataclass
class PlanItem:
    action: ActionName
    profile_id: str
    kind: str
    relpath: str
    reason: str
    local: Optional[FileRecord] = None
    remote: Optional[FileRecord] = None
    will_overwrite: bool = False

    @property
    def key(self) -> str:
        return f"{self.profile_id}/{self.kind}/{self.relpath}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "profile_id": self.profile_id,
            "kind": self.kind,
            "relpath": self.relpath,
            "reason": self.reason,
            "will_overwrite": self.will_overwrite,
            "local": None if self.local is None else self.local.as_dict(),
            "remote": None if self.remote is None else self.remote.as_dict(),
        }


@dataclass
class SyncPlan:
    items: list[PlanItem] = field(default_factory=list)
    target_type: str = "folder"
    target_path: str = ""
    notes: list[str] = field(default_factory=list)

    def by_action(self, action: ActionName) -> list[PlanItem]:
        return [i for i in self.items if i.action == action]

    @property
    def pushes(self) -> list[PlanItem]:
        return self.by_action("push")

    @property
    def pulls(self) -> list[PlanItem]:
        return self.by_action("pull")

    @property
    def conflicts(self) -> list[PlanItem]:
        return self.by_action("conflict")

    @property
    def skips(self) -> list[PlanItem]:
        return self.by_action("skip")

    @property
    def overwrites(self) -> list[PlanItem]:
        return [i for i in self.items if i.will_overwrite]

    def summary(self) -> dict[str, int]:
        return {
            "push": len(self.pushes),
            "pull": len(self.pulls),
            "conflict": len(self.conflicts),
            "skip": len(self.skips),
            "overwrite": len(self.overwrites),
            "total": len(self.items),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_path": self.target_path,
            "summary": self.summary(),
            "notes": list(self.notes),
            "items": [i.as_dict() for i in self.items],
        }


def iter_action(items: Iterable[PlanItem], action: ActionName) -> list[PlanItem]:
    return [i for i in items if i.action == action]

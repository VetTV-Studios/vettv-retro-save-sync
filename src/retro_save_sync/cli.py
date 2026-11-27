from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from retro_save_sync import APP_NAME, __version__
from retro_save_sync.backup import RestoreError, list_backups, restore_backup
from retro_save_sync.config import AppConfig, SyncTarget, load_config
from retro_save_sync.detect import format_profile_line
from retro_save_sync.engine import apply_plan, preview, scan
from retro_save_sync.targets import rclone_status
from retro_save_sync.util import format_bytes


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    cfg = load_config(
        config_path=getattr(args, "config", None),
        root=getattr(args, "root", None),
        platform=getattr(args, "platform", None),
        backup_root=getattr(args, "backup_root", None),
    )
    target_path = getattr(args, "target", None)
    target_type = getattr(args, "target_type", None)
    remote = getattr(args, "remote", None)
    if target_type:
        cfg.target.type = target_type
    if target_path:
        cfg.target.path = target_path
    if remote:
        cfg.target.remote = remote
        if not target_type:
            cfg.target.type = "rclone"
    return cfg


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_scan(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    result = scan(cfg, include_missing=not args.found_only)
    if args.json:
        _print_json(
            {
                "root": str(cfg.root),
                "platform": cfg.platform,
                "profiles": [p.as_public_dict() for p in result.profiles],
                "files": len(result.local_index),
            }
        )
        return 0
    print(f"{APP_NAME} scan")
    print(f"  root      {cfg.root}")
    print(f"  platform  {cfg.platform}")
    print()
    if not result.profiles:
        print("No profiles detected.")
        return 0
    for profile in result.profiles:
        print("  " + format_profile_line(profile))
    present = [p for p in result.profiles if p.present]
    total_files = sum(p.file_count for p in present)
    total_bytes = sum(p.total_bytes for p in present)
    print()
    print(f"  {len(present)} present / {len(result.profiles)} profiles, {total_files} files, {format_bytes(total_bytes)}")
    return 0


def _print_plan(plan) -> None:
    summary = plan.summary()
    print(f"{APP_NAME} preview")
    print(f"  target    {plan.target_type}  {plan.target_path}")
    print(
        f"  plan      {summary['push']} push, {summary['pull']} pull, "
        f"{summary['conflict']} conflict, {summary['skip']} skip "
        f"({summary['overwrite']} overwrites)"
    )
    for note in plan.notes:
        print(f"  note      {note}")
    print()
    if not plan.items:
        print("  (nothing to sync)")
        return
    width = max((len(i.key) for i in plan.items), default=8)
    for item in plan.items:
        if item.action == "skip" and not sys.stdout.isatty():
            # Still show skips; they prove the comparator ran. Keep them compact.
            pass
        flag = "OVERWRITE" if item.will_overwrite else ""
        print(f"  {item.action.upper():9}  {item.key:<{width}}  {item.reason}  {flag}".rstrip())


def cmd_preview(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    plan = preview(cfg)
    if args.json:
        _print_json(plan.as_dict())
        return 0
    _print_plan(plan)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    if args.dry_run:
        plan = preview(cfg)
        if args.json:
            _print_json(plan.as_dict())
        else:
            _print_plan(plan)
        return 0
    result = apply_plan(cfg, dry_run=False)
    if args.json:
        _print_json(result.as_dict())
        return 0
    _print_plan(result.plan)
    print()
    print(f"  applied   {len(result.applied)} file(s)")
    if result.backup:
        print(f"  backup    {result.backup.id}  ({len(result.backup.files)} file(s) snapshotted)")
    else:
        print("  backup    (none — no overwrites)")
    if result.git:
        print(f"  git       committed={result.git.get('committed')} pushed={result.git.get('pushed')}")
    if result.rclone:
        print(f"  rclone    ok={result.rclone.get('ok')} dry_run={result.rclone.get('dry_run')}")
    if result.skipped_conflicts:
        print(f"  conflicts {len(result.skipped_conflicts)} left untouched")
        return 2
    return 0


def cmd_backups(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    backups = list_backups(cfg.dirs.backup_dir)
    if args.json:
        _print_json({"backup_root": str(cfg.dirs.backup_dir), "backups": [b.as_dict() for b in backups]})
        return 0
    print(f"{APP_NAME} backups")
    print(f"  root      {cfg.dirs.backup_dir}")
    if not backups:
        print("  (none)")
        return 0
    print()
    for backup in backups:
        print(
            f"  {backup.id}  {backup.created}  {backup.operation}  "
            f"{len(backup.files)} file(s)  {backup.target_type}"
        )
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    try:
        result = restore_backup(cfg.dirs.backup_dir, args.backup_id, verify=not args.no_verify)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except RestoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for row in exc.mismatches:
            print(f"  {row['path']}: expected {row['expected']} got {row['actual']}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(result)
        return 0
    print(f"{APP_NAME} restore")
    print(f"  backup    {result['id']}")
    print(f"  restored  {result['count']} file(s)")
    print(f"  verified  {result['verified']} (SHA-256)")
    for row in result["restored"]:
        print(f"  ok        {row['path']}  {row['actual'][:12]}…")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    info = {
        "version": __version__,
        "root": str(cfg.root),
        "platform": cfg.platform,
        "config": str(cfg.path) if cfg.path else None,
        "backup_root": str(cfg.dirs.backup_dir),
        "target": cfg.target.as_dict(),
        "rclone": rclone_status(),
    }
    if args.json:
        _print_json(info)
        return 0
    print(f"{APP_NAME} {__version__}")
    for key, value in info.items():
        if key in {"version"}:
            continue
        print(f"  {key:12} {value}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from retro_save_sync.gui import run_gui

    cfg = _config_from_args(args)
    return run_gui(
        cfg,
        screenshot=args.screenshot,
        demo=args.demo,
    )


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Path to config.json")
    parser.add_argument("--root", help="Override user root (fake HOME / USERPROFILE for tests)")
    parser.add_argument("--platform", choices=["linux", "windows"], help="Path map to use")
    parser.add_argument("--backup-root", dest="backup_root", help="Override backup directory")
    parser.add_argument("--target", help="Sync target path (folder, git work tree, or bare repo)")
    parser.add_argument("--target-type", dest="target_type", choices=["folder", "git", "rclone"], help="Sync target type")
    parser.add_argument("--remote", help="rclone remote spec (e.g. gdrive:vettv-saves)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retro-save-sync",
        description="VetTV Retro Save Sync — detect, preview, sync, and roll back emulator saves.",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Detect emulator save paths and list files")
    _add_shared(scan_p)
    scan_p.add_argument("--found-only", action="store_true", help="Hide profiles whose folders are missing")
    scan_p.set_defaults(func=cmd_scan)

    preview_p = sub.add_parser("preview", help="Dry-run preview of push / pull / conflict")
    _add_shared(preview_p)
    preview_p.set_defaults(func=cmd_preview)

    sync_p = sub.add_parser("sync", help="Apply a sync (creates timestamped rollback backups before overwrites)")
    _add_shared(sync_p)
    sync_p.add_argument("--dry-run", action="store_true", help="Show the plan only; do not write")
    sync_p.set_defaults(func=cmd_sync)

    backups_p = sub.add_parser("backups", help="List timestamped rollback backups")
    _add_shared(backups_p)
    backups_p.set_defaults(func=cmd_backups)

    restore_p = sub.add_parser("restore", help="Restore a rollback backup and verify SHA-256")
    _add_shared(restore_p)
    restore_p.add_argument("backup_id", help="Backup id (YYYYMMDD-HHMMSS)")
    restore_p.add_argument("--no-verify", action="store_true", help="Skip SHA-256 verification (not recommended)")
    restore_p.set_defaults(func=cmd_restore)

    status_p = sub.add_parser("status", help="Show config, target, and rclone availability")
    _add_shared(status_p)
    status_p.set_defaults(func=cmd_status)

    gui_p = sub.add_parser("gui", help="Open the desktop GUI")
    _add_shared(gui_p)
    gui_p.add_argument("--screenshot", help="Render the window and save a PNG, then exit")
    gui_p.add_argument("--demo", action="store_true", help="Seed a local demo fixture if the root is empty")
    gui_p.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        if "--json" in (argv or sys.argv):
            _print_json({"error": str(exc)})
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

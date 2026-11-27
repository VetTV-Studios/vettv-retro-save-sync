from __future__ import annotations

import sys
from pathlib import Path

from retro_save_sync import APP_NAME, ORG_NAME, __version__
from retro_save_sync.backup import RestoreError, list_backups, restore_backup
from retro_save_sync.config import AppConfig
from retro_save_sync.engine import apply_plan, preview, scan
from retro_save_sync.targets import rclone_status
from retro_save_sync.util import format_bytes, now_iso

QSS = """
QMainWindow, QWidget, QDialog {
  background: #07020f;
  color: #f7e9ff;
  font-family: "Noto Sans", "DejaVu Sans", "Segoe UI", "Ubuntu", sans-serif;
  font-size: 13px;
}
QLabel#brandMark {
  color: #ffffff;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
}
QLabel#brandTv {
  background: #ff2d55;
  color: #0b0414;
  font-size: 22px;
  font-weight: 900;
  border-radius: 6px;
  padding: 0 8px;
}
QLabel#appTitle {
  color: #ffd23f;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 1px;
}
QLabel#subtitle {
  color: #c9a8d8;
  font-size: 12px;
}
QLabel#clock {
  color: #22e6ff;
  font-size: 18px;
  font-weight: 700;
  font-family: "DejaVu Sans Mono", "Consolas", monospace;
}
QFrame#topBar, QFrame#card, QFrame#footer {
  background: rgba(14, 6, 28, 0.88);
  border: 1px solid rgba(255, 79, 216, 0.45);
  border-radius: 12px;
}
QFrame#footer {
  border-color: rgba(255, 45, 85, 0.7);
}
QLabel#section {
  color: #22e6ff;
  font-weight: 800;
  letter-spacing: 1.4px;
  font-size: 12px;
}
QPushButton {
  background: #1a0830;
  color: #f7e9ff;
  border: 1px solid rgba(34, 230, 255, 0.55);
  border-radius: 8px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton:hover { background: #2a0f48; border-color: #22e6ff; }
QPushButton:disabled { color: #6b5278; border-color: #3a2748; }
QPushButton#primary {
  background: #22e6ff;
  color: #07020f;
  border: none;
}
QPushButton#primary:hover { background: #7af3ff; }
QPushButton#danger {
  background: #ff2d55;
  color: #fff;
  border: none;
}
QPushButton#danger:hover { background: #ff5d7c; }
QComboBox, QLineEdit {
  background: #12061e;
  color: #fff;
  border: 1px solid rgba(34, 230, 255, 0.4);
  border-radius: 6px;
  padding: 6px 8px;
  min-height: 28px;
}
QComboBox QAbstractItemView {
  background: #12061e;
  color: #fff;
  selection-background-color: #2a0f48;
}
QTableWidget, QListWidget, QTreeWidget {
  background: #10051a;
  alternate-background-color: #160826;
  color: #f7e9ff;
  border: 1px solid rgba(255, 79, 216, 0.35);
  border-radius: 8px;
  gridline-color: rgba(255, 255, 255, 0.06);
  selection-background-color: #2a0f48;
  selection-color: #fff;
}
QHeaderView::section {
  background: #1a0830;
  color: #ffd9f4;
  border: none;
  padding: 6px 8px;
  font-weight: 700;
}
QStatusBar { background: transparent; color: #c9a8d8; }
QScrollBar:vertical, QScrollBar:horizontal {
  background: #10051a; width: 10px; height: 10px; border: none;
}
QScrollBar::handle { background: #4a2068; border-radius: 4px; }
QMessageBox { background: #07020f; }
"""


def run_gui(cfg: AppConfig, *, screenshot: str | None = None, demo: bool = False) -> int:
    if demo:
        from retro_save_sync.demo import maybe_seed

        seeded = maybe_seed(cfg.root, platform=cfg.platform)
        if seeded is not None:
            cfg = seeded

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    class MainWindow(QMainWindow):
        def __init__(self, config: AppConfig):
            super().__init__()
            self.cfg = config
            self.setWindowTitle(f"{APP_NAME}  ·  {ORG_NAME}")
            self.resize(1920, 1080)
            self.setMinimumSize(1280, 800)
            root = QWidget()
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            layout.setContentsMargins(16, 16, 16, 12)
            layout.setSpacing(12)
            layout.addWidget(self._top_bar())

            body = QHBoxLayout()
            body.setSpacing(12)
            left = self._profiles_card()
            right = QVBoxLayout()
            right.setSpacing(12)
            right.addWidget(self._target_card())
            right.addWidget(self._preview_card(), 3)
            right.addWidget(self._backup_card(), 2)
            wrap = QWidget()
            wrap.setLayout(right)
            body.addWidget(left, 2)
            body.addWidget(wrap, 3)
            layout.addLayout(body, 1)
            layout.addWidget(self._footer())
            self.refresh_all()

        def _card(self) -> QFrame:
            frame = QFrame()
            frame.setObjectName("card")
            return frame

        def _top_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("topBar")
            bar.setFixedHeight(78)
            row = QHBoxLayout(bar)
            row.setContentsMargins(16, 10, 16, 10)
            mark = QLabel("Vet")
            mark.setObjectName("brandMark")
            tv = QLabel("TV")
            tv.setObjectName("brandTv")
            title = QLabel("  RETRO SAVE SYNC")
            title.setObjectName("appTitle")
            sub = QLabel("Safe sync for RetroArch · PCSX2 · Dolphin · custom paths")
            sub.setObjectName("subtitle")
            brand_col = QVBoxLayout()
            brand_row = QHBoxLayout()
            brand_row.setSpacing(6)
            brand_row.addWidget(mark)
            brand_row.addWidget(tv)
            brand_row.addWidget(title)
            brand_row.addStretch()
            brand_col.addLayout(brand_row)
            brand_col.addWidget(sub)
            row.addLayout(brand_col, 1)
            right = QVBoxLayout()
            self.clock = QLabel(now_iso())
            self.clock.setObjectName("clock")
            self.clock.setAlignment(Qt.AlignRight)
            ver = QLabel(f"v{__version__}   {self.cfg.platform.upper()}   LIVE")
            ver.setObjectName("subtitle")
            ver.setAlignment(Qt.AlignRight)
            right.addWidget(self.clock)
            right.addWidget(ver)
            row.addLayout(right)
            self._timer = QTimer(self)
            self._timer.timeout.connect(lambda: self.clock.setText(now_iso()))
            self._timer.start(1000)
            return bar

        def _section(self, text: str) -> QLabel:
            label = QLabel(text.upper())
            label.setObjectName("section")
            return label

        def _profiles_card(self) -> QFrame:
            card = self._card()
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 12, 14, 12)
            header = QHBoxLayout()
            header.addWidget(self._section("Detected profiles"))
            header.addStretch()
            refresh = QPushButton("Rescan")
            refresh.clicked.connect(self.refresh_all)
            header.addWidget(refresh)
            col.addLayout(header)
            self.profile_table = QTableWidget(0, 5)
            self.profile_table.setHorizontalHeaderLabels(["Profile", "Variant", "Status", "Files", "Size"])
            self.profile_table.horizontalHeader().setStretchLastSection(True)
            self.profile_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.profile_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.profile_table.setAlternatingRowColors(True)
            self.profile_table.verticalHeader().setVisible(False)
            col.addWidget(self.profile_table, 1)
            self.paths_label = QLabel()
            self.paths_label.setObjectName("subtitle")
            self.paths_label.setWordWrap(True)
            col.addWidget(self.paths_label)
            return card

        def _target_card(self) -> QFrame:
            card = self._card()
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 12, 14, 12)
            col.addWidget(self._section("Sync target"))
            row = QHBoxLayout()
            self.target_type = QComboBox()
            self.target_type.addItems(["folder", "git", "rclone"])
            self.target_type.setCurrentText(self.cfg.target.type)
            self.target_path = QLineEdit(self.cfg.target.display_path() if self.cfg.target.display_path() != "(not set)" else "")
            self.target_path.setPlaceholderText("Folder, git repo, or rclone remote (gdrive:saves)")
            browse = QPushButton("Browse")
            browse.clicked.connect(self._browse_target)
            row.addWidget(self.target_type)
            row.addWidget(self.target_path, 1)
            row.addWidget(browse)
            col.addLayout(row)
            actions = QHBoxLayout()
            self.preview_btn = QPushButton("Dry-Run Preview")
            self.preview_btn.setObjectName("primary")
            self.preview_btn.clicked.connect(self.run_preview)
            self.sync_btn = QPushButton("Sync Now")
            self.sync_btn.clicked.connect(self.run_sync)
            actions.addWidget(self.preview_btn)
            actions.addWidget(self.sync_btn)
            actions.addStretch()
            self.target_hint = QLabel()
            self.target_hint.setObjectName("subtitle")
            actions.addWidget(self.target_hint)
            col.addLayout(actions)
            return card

        def _preview_card(self) -> QFrame:
            card = self._card()
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 12, 14, 12)
            head = QHBoxLayout()
            head.addWidget(self._section("Dry-run preview"))
            head.addStretch()
            self.preview_summary = QLabel("Run a preview to see push / pull / conflict")
            self.preview_summary.setObjectName("subtitle")
            head.addWidget(self.preview_summary)
            col.addLayout(head)
            self.plan_table = QTableWidget(0, 5)
            self.plan_table.setHorizontalHeaderLabels(["Action", "File", "Overwrite", "Reason", "SHA (local → target)"])
            self.plan_table.horizontalHeader().setStretchLastSection(True)
            self.plan_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.plan_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.plan_table.setAlternatingRowColors(True)
            self.plan_table.verticalHeader().setVisible(False)
            col.addWidget(self.plan_table, 1)
            return card

        def _backup_card(self) -> QFrame:
            card = self._card()
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 12, 14, 12)
            head = QHBoxLayout()
            head.addWidget(self._section("Backup / Rollback Manager"))
            head.addStretch()
            restore = QPushButton("Restore Selected")
            restore.setObjectName("danger")
            restore.clicked.connect(self.run_restore)
            head.addWidget(restore)
            col.addLayout(head)
            self.backup_table = QTableWidget(0, 4)
            self.backup_table.setHorizontalHeaderLabels(["Backup ID", "Created (CT)", "Files", "Operation"])
            self.backup_table.horizontalHeader().setStretchLastSection(True)
            self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.backup_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.backup_table.setAlternatingRowColors(True)
            self.backup_table.verticalHeader().setVisible(False)
            col.addWidget(self.backup_table, 1)
            return card

        def _footer(self) -> QFrame:
            footer = QFrame()
            footer.setObjectName("footer")
            footer.setFixedHeight(42)
            row = QHBoxLayout(footer)
            row.setContentsMargins(14, 0, 14, 0)
            note = QLabel(
                "Independent VetTV tool. Original art only. Never bundles copyrighted games, ROMs, or BIOS. "
                "Conflicts are never overwritten silently. Every overwrite is snapshotted first."
            )
            note.setObjectName("subtitle")
            row.addWidget(note)
            return footer

        def _apply_target(self) -> None:
            self.cfg.target.type = self.target_type.currentText()  # type: ignore[assignment]
            value = self.target_path.text().strip()
            if self.cfg.target.type == "rclone":
                self.cfg.target.remote = value
            else:
                self.cfg.target.path = value

        def _browse_target(self) -> None:
            start = self.target_path.text().strip() or str(self.cfg.root)
            chosen = QFileDialog.getExistingDirectory(self, "Choose sync folder / git repo", start)
            if chosen:
                self.target_path.setText(chosen)
                if self.target_type.currentText() == "rclone":
                    self.target_type.setCurrentText("folder")

        def refresh_all(self) -> None:
            result = scan(self.cfg, include_missing=True)
            self._fill_profiles(result.profiles)
            self._fill_backups()
            rc = rclone_status()
            hint = "rclone: available" if rc.get("available") else "rclone: not installed (folder & git still work)"
            self.target_hint.setText(hint)
            try:
                self.run_preview(silent=True)
            except Exception as exc:  # noqa: BLE001
                self.preview_summary.setText(str(exc))

        def _fill_profiles(self, profiles) -> None:
            self.profile_table.setRowCount(len(profiles))
            lines = []
            for row, profile in enumerate(profiles):
                values = [
                    profile.name,
                    profile.variant,
                    "FOUND" if profile.present else "missing",
                    str(profile.file_count) if profile.present else "—",
                    format_bytes(profile.total_bytes) if profile.present else "—",
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 2 and profile.present:
                        item.setForeground(QColor("#22e6ff"))
                    elif col == 2:
                        item.setForeground(QColor("#6b5278"))
                    self.profile_table.setItem(row, col, item)
                if profile.present:
                    roots = "; ".join(f"{r.kind}: {r.path}" for r in profile.roots if r.path.exists())
                    lines.append(f"{profile.name}: {roots}")
            self.profile_table.resizeColumnsToContents()
            self.paths_label.setText("\n".join(lines[:8]) or "No emulator folders found under this root.")

        def _fill_plan(self, plan) -> None:
            items = [i for i in plan.items if i.action != "skip"] or plan.items
            # Show skips too if the interesting set is small, but cap for readability.
            interesting = [i for i in plan.items if i.action != "skip"]
            display = interesting if interesting else plan.items
            self.plan_table.setRowCount(len(display))
            colors = {
                "push": QColor("#22e6ff"),
                "pull": QColor("#ffd23f"),
                "conflict": QColor("#ff2d55"),
                "skip": QColor("#c9a8d8"),
            }
            for row, item in enumerate(display):
                sha = ""
                if item.local and item.remote:
                    sha = f"{item.local.sha256[:10]}… → {item.remote.sha256[:10]}…"
                elif item.local:
                    sha = f"{item.local.sha256[:10]}… → (new)"
                elif item.remote:
                    sha = f"(new) ← {item.remote.sha256[:10]}…"
                values = [
                    item.action.upper(),
                    item.key,
                    "yes" if item.will_overwrite else "no",
                    item.reason,
                    sha,
                ]
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if col == 0:
                        cell.setForeground(colors.get(item.action, QColor("#fff")))
                    self.plan_table.setItem(row, col, cell)
            self.plan_table.resizeColumnsToContents()
            s = plan.summary()
            self.preview_summary.setText(
                f"{s['push']} push · {s['pull']} pull · {s['conflict']} conflict · "
                f"{s['skip']} in sync · {s['overwrite']} overwrite"
                + ("" if not plan.notes else "  |  " + " · ".join(plan.notes[:2]))
            )

        def _fill_backups(self) -> None:
            backups = list_backups(self.cfg.dirs.backup_dir)
            self.backup_table.setRowCount(len(backups))
            for row, backup in enumerate(backups):
                values = [backup.id, backup.created, str(len(backup.files)), backup.operation]
                for col, value in enumerate(values):
                    self.backup_table.setItem(row, col, QTableWidgetItem(value))
            self.backup_table.resizeColumnsToContents()

        def run_preview(self, silent: bool = False) -> None:
            self._apply_target()
            plan = preview(self.cfg)
            self._fill_plan(plan)
            if not silent:
                self.statusBar().showMessage("Dry-run preview ready — no files were written.", 6000)

        def run_sync(self) -> None:
            self._apply_target()
            plan = preview(self.cfg)
            if plan.conflicts:
                answer = QMessageBox.question(
                    self,
                    "Conflicts present",
                    f"{len(plan.conflicts)} conflicting save(s) will be left untouched. "
                    "Continue with the safe push/pull items only?",
                )
                if answer != QMessageBox.Yes:
                    return
            try:
                result = apply_plan(self.cfg, plan, dry_run=False)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Sync failed", str(exc))
                return
            self.refresh_all()
            backup = f"\nRollback backup: {result.backup.id}" if result.backup else "\nNo overwrites, so no backup was needed."
            QMessageBox.information(
                self,
                "Sync complete",
                f"Applied {len(result.applied)} file(s). "
                f"{len(result.skipped_conflicts)} conflict(s) left untouched.{backup}",
            )

        def run_restore(self) -> None:
            row = self.backup_table.currentRow()
            if row < 0:
                QMessageBox.information(self, "No backup selected", "Select a backup row first.")
                return
            backup_id = self.backup_table.item(row, 0).text()
            answer = QMessageBox.question(
                self,
                "Restore backup",
                f"Restore backup {backup_id} and verify SHA-256 of every file?",
            )
            if answer != QMessageBox.Yes:
                return
            try:
                result = restore_backup(self.cfg.dirs.backup_dir, backup_id, verify=True)
            except RestoreError as exc:
                QMessageBox.critical(self, "Restore failed verification", str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Restore failed", str(exc))
                return
            self.refresh_all()
            QMessageBox.information(
                self,
                "Restore complete",
                f"Restored {result['count']} file(s). SHA-256 verified: {result['verified']}.",
            )

        def capture(self, dest: Path) -> None:
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            pix = self.grab()
            if pix.width() < 1200:
                # Composite onto a branded 1600x980 canvas if the grab is small.
                canvas = QPixmap(1600, 980)
                canvas.fill(QColor("#07020f"))
                painter = QPainter(canvas)
                painter.drawPixmap(0, 0, pix)
                painter.end()
                pix = canvas
            pix.save(str(dest), "PNG")

    # Qt also parses --platform from argv; our CLI uses that flag for the
    # OS path map, so never hand the raw argv to QApplication.
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyleSheet(QSS)
    window = MainWindow(cfg)
    window.show()
    # Pump until the first layout is real, then optionally screenshot and exit.
    app.processEvents()
    window.repaint()
    app.processEvents()
    if screenshot:
        # A couple extra frames so tables finish resizing.
        QTimer.singleShot(250, lambda: None)
        app.processEvents()
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        QTimer.singleShot(400, loop.quit)
        loop.exec()
        window.capture(Path(screenshot))
        window.close()
        return 0
    return app.exec()

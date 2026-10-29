"""Backup and restore."""
from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from app.config import backups_dir, db_path
from app.services.backup_service import validate_backup
from app.ui.reusable_widgets import (PageHeader, button, card, confirm, fill_table, guarded, info, make_table, muted,
                                     open_path, run_task, selected_key, subtitle, ts)


class BackupPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        lay.addWidget(PageHeader("Backup", "Protect your customers and sales"))
        row = QHBoxLayout()
        b = button("Back up now", "primary", "backup"); b.clicked.connect(self.backup)
        b2 = button("Back up to a file / USB…", icon_name="download"); b2.clicked.connect(self.backup_to)
        r = button("Restore from a backup…", "danger", "upload"); r.clicked.connect(self.restore)
        o = button("Open backup folder"); o.clicked.connect(lambda: open_path(backups_dir()))
        for x in (b, b2, r, o):
            row.addWidget(x)
        row.addStretch(1)
        lay.addLayout(row)
        self.table = make_table(["Backup file", "Created", "Size"], 0)
        self.table.setMinimumHeight(260)
        lay.addWidget(card(subtitle("Backups on this PC"), self.table))
        v = button("Check selected backup", icon_name="check"); v.clicked.connect(self.validate)
        lay.addWidget(v)
        lay.addWidget(card(subtitle("Keep backups safe"), muted(
            "Backups contain personal data and the full sales history. Copy them regularly to an encrypted USB drive or "
            "another PC, keep at least one copy off-site, and never e-mail them. Restoring first saves a safety copy of "
            "the current data (before_restore_…db), checks the backup and then replaces the data. Live database: "
            f"{db_path()}")))
        lay.addStretch(1)

    def refresh(self):
        files = self.ctx.backup.list_backups()
        fill_table(self.table, [[f.name, ts(f.stat().st_mtime), f"{f.stat().st_size / 1e6:.1f} MB"] for f in files],
                   [str(f) for f in files])

    def backup(self):
        run_task(self, "Backing up…", self.ctx.backup.backup,
                 lambda p: (info(self, "Backup", f"Backup created:\n{p}"), self.refresh()))

    def backup_to(self):
        p, _ = QFileDialog.getSaveFileName(self, "Backup file", f"nomloyal_{time.strftime('%Y%m%d_%H%M')}.db",
                                           "NomLoyal backup (*.db)")
        if p:
            run_task(self, "Backing up…", lambda: self.ctx.backup.backup(p),
                     lambda out: info(self, "Backup", f"Backup created:\n{out}"))

    def validate(self):
        p = selected_key(self.table)
        if p:
            ok, i = guarded(self, "Backup", validate_backup, p)
            if ok:
                info(self, "Backup", f"The backup is valid.\nCustomers: {i['customers']}\nSales: {i['sales']}\n"
                                     f"Schema version: {i['version']}")

    def restore(self):
        p, _ = QFileDialog.getOpenFileName(self, "Restore backup", str(backups_dir()), "NomLoyal backup (*.db)")
        if not p:
            return
        ok, i = guarded(self, "Restore", validate_backup, p)
        if not ok:
            return
        if not confirm(self, "Restore", f"Replace ALL current data with this backup?\n\nBackup: {i['customers']} customers, "
                                        f"{i['sales']} sales.\nA safety copy of the current data is made first. "
                                        "NomLoyal will close afterwards - start it again.", True):
            return
        ok, safety = guarded(self, "Restore", self.ctx.backup.restore, p)
        if ok:
            info(self, "Restore", f"Restored. Your previous data was saved as:\n{safety}\n\nNomLoyal will now close.")
            self.main.ctx.auth.user = None
            QApplication.instance().quit()

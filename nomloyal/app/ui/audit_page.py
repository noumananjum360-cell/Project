"""Audit log viewer (append-only)."""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from app.config import exports_dir
from app.services.reporting_service import range_bounds
from app.ui.reusable_widgets import DateRange, PageHeader, button, fill_table, guarded, info, make_table, muted, ts


class AuditPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Audit Log", "Every sign-in, change, export and deletion - entries cannot be edited or deleted")
        x = h.add(button("Export CSV", icon_name="download")); x.clicked.connect(self.export)
        lay.addWidget(h)
        bar = QHBoxLayout()
        self.range = DateRange(7); self.range.changed.connect(self.refresh)
        self.q = QLineEdit(); self.q.setPlaceholderText("Filter by user, action or record"); self.q.returnPressed.connect(self.refresh)
        go = button("Search", icon_name="search"); go.clicked.connect(self.refresh)
        bar.addWidget(self.range); bar.addWidget(self.q, 1); bar.addWidget(go)
        lay.addLayout(bar)
        self.table = make_table(["When", "User", "Action", "Record", "ID", "Details"], 5)
        lay.addWidget(self.table, 1)
        self.count = muted(); lay.addWidget(self.count)

    def _rows(self):
        self.ctx.auth.require("audit.view")
        t0, t1 = range_bounds(*self.range.range())
        q = f"%{self.q.text().strip()}%"
        return self.ctx.db.q("SELECT * FROM audit_log WHERE ts>=? AND ts<? AND (username LIKE ? OR action LIKE ? OR "
                             "entity LIKE ? OR details LIKE ?) ORDER BY id DESC LIMIT 5000", (t0, t1, q, q, q, q))

    def refresh(self):
        rows = self._rows()
        fill_table(self.table, [[ts(r["ts"]), r["username"], r["action"], r["entity"], r["entity_id"], r["details"]]
                                for r in rows])
        self.count.setText(f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}")

    def export(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export audit log", str(exports_dir() / "audit_log.csv"), "CSV (*.csv)")
        if p:
            rows = [dict(r) for r in self._rows()]
            cols = [("ts", "When"), ("username", "User"), ("action", "Action"), ("entity", "Record"), ("entity_id", "ID"),
                    ("details", "Details")]
            if guarded(self, "Export", self.ctx.reports.export_csv, rows, cols, p, "audit_log")[0]:
                info(self, "Export", "Audit log exported.")

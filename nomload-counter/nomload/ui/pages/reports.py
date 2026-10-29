"""Reports: certificates, daily dispatch, mismatch report, Excel export, audit log."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QDateEdit, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
                               QVBoxLayout, QWidget)

from nomload.i18n import _
from nomload.services.reports import fmt_ts
from nomload.ui.pages.common import open_file, report_path
from nomload.ui.widgets import Card, PageHeader, button, error, fill_table, make_table, run_async


def _date(days_back=0):
    d = QDateEdit(QDate.currentDate().addDays(-days_back))
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd-MMM-yyyy")
    return d


class ReportsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        lay.addWidget(PageHeader("Reports"))
        g = QGridLayout()
        g.setSpacing(14)
        # certificate
        c = Card("Truck loading certificate")
        h = QHBoxLayout()
        self.cert_id = QSpinBox()
        self.cert_id.setRange(1, 10 ** 9)
        self.cert_id.setPrefix(_("Session #"))
        b = button("Generate PDF", "Primary", "reports")
        b.clicked.connect(self.cert)
        h.addWidget(self.cert_id, 1)
        h.addWidget(b)
        c.lay.addLayout(h)
        g.addWidget(c, 0, 0)
        # daily
        c = Card("Daily dispatch summary")
        h = QHBoxLayout()
        self.day = _date()
        b = button("Generate PDF", "Primary", "reports")
        b.clicked.connect(self.daily)
        h.addWidget(self.day, 1)
        h.addWidget(b)
        c.lay.addLayout(h)
        g.addWidget(c, 0, 1)
        # mismatch
        c = Card("Mismatch report")
        h = QHBoxLayout()
        self.m0, self.m1 = _date(30), _date()
        b = button("Generate PDF", "Primary", "reports")
        b.clicked.connect(self.mismatch)
        h.addWidget(self.m0, 1)
        h.addWidget(self.m1, 1)
        h.addWidget(b)
        c.lay.addLayout(h)
        g.addWidget(c, 1, 0)
        # excel
        c = Card("Excel export")
        h = QHBoxLayout()
        self.x0, self.x1 = _date(30), _date()
        b = button("Export .xlsx", "Primary", "download")
        b.clicked.connect(self.excel)
        h.addWidget(self.x0, 1)
        h.addWidget(self.x1, 1)
        h.addWidget(b)
        c.lay.addLayout(h)
        g.addWidget(c, 1, 1)
        lay.addLayout(g)
        # audit log
        self.audit_card = Card("Audit log")
        h = QHBoxLayout()
        self.a_filter = QLineEdit()
        self.a_filter.setPlaceholderText(_("Filter by user, action or details"))
        self.a_filter.returnPressed.connect(self.load_audit)
        rb = button("Refresh", icon_name="refresh")
        rb.clicked.connect(self.load_audit)
        h.addWidget(self.a_filter, 1)
        h.addWidget(rb)
        self.audit_card.lay.addLayout(h)
        self.audit = make_table(["Time", "User", "Action", "Entity", "Details"], 4)
        self.audit_card.lay.addWidget(self.audit)
        lay.addWidget(self.audit_card, 1)

    def _muted(self, t):
        l = QLabel(_(t))
        l.setObjectName("Muted")
        l.setWordWrap(True)
        return l

    def showEvent(self, e):
        super().showEvent(e)
        last = self.app.db.scalar("SELECT MAX(id) FROM sessions WHERE deleted=0")
        if last:
            self.cert_id.setValue(last)
        self.audit_card.setVisible(bool(self.app.user and self.app.user.can("view_audit")))
        self.load_audit()

    def load_audit(self):
        if not self.audit_card.isVisible():
            return
        q = self.a_filter.text().strip()
        if q:
            rows = self.app.db.q("SELECT * FROM audit_log WHERE username LIKE ? OR action LIKE ? OR details LIKE ? "
                                 "ORDER BY id DESC LIMIT 500", (f"%{q}%",) * 3)
        else:
            rows = self.app.db.q("SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")
        fill_table(self.audit, [[fmt_ts(r["ts"]), r["username"], r["action"], f"{r['entity']} {r['entity_id']}",
                                 r["details"][:240]] for r in rows])

    def _run(self, fn, path):
        def done(_r):
            from nomload.services.context import audit
            audit(self.app.db, self.app.user, "report_generated", "report", path.name)
            open_file(path)

        run_async(self, lambda: fn(path), done, lambda m: error(self, f"{_('Report failed')}: {m}"),
                  busy=_("Creating report..."))

    def cert(self):
        sid = self.cert_id.value()
        self._run(lambda p: self.app.reports.loading_certificate(sid, p), report_path(f"certificate_session_{sid}.pdf"))

    def daily(self):
        d = self.day.date().toPython()
        self._run(lambda p: self.app.reports.daily_dispatch(d, p), report_path(f"daily_dispatch_{d.isoformat()}.pdf"))

    def mismatch(self):
        a, b = self.m0.date().toPython(), self.m1.date().toPython()
        self._run(lambda p: self.app.reports.mismatch_report(a, b, p), report_path(f"mismatch_{a}_{b}.pdf"))

    def excel(self):
        a, b = self.x0.date().toPython(), self.x1.date().toPython()
        p, _f = QFileDialog.getSaveFileName(self, _("Export to Excel"), str(report_path(f"nomload_{a}_{b}.xlsx")),
                                            "Excel (*.xlsx)")
        if p:
            from pathlib import Path
            self._run(lambda q: self.app.reports.export_excel(a, b, q), Path(p))

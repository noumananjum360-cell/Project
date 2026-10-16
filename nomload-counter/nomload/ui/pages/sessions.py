"""Sessions: gate passes (manual / CSV / Excel), today's sessions and the review queue."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from nomload import theme
from nomload.i18n import _
from nomload.services.catalog import write_import_template
from nomload.services.reports import STATUS_LABEL, day_bounds
from nomload.ui.dialogs import GatePassDialog, ReviewDialog, ask_supervisor
from nomload.ui.pages.common import open_file
from nomload.ui.widgets import PageHeader, button, confirm, error, fill_table, info, make_table, selected_data


class SessionsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(PageHeader("Sessions"))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        # -------- gate passes
        gp = QWidget()
        gl = QVBoxLayout(gp)
        gl.setContentsMargins(0, 12, 0, 0)
        bar = QHBoxLayout()
        self.gp_search = QLineEdit()
        self.gp_search.setPlaceholderText(_("Search gate pass, vehicle or customer"))
        self.gp_search.textChanged.connect(self.load_gate_passes)
        self.gp_status = QComboBox()
        for k, v in (("open,loading", _("Open & loading")), ("open", _("Open")), ("loading", _("Loading")),
                     ("completed", _("Completed")), ("cancelled", _("Cancelled")), ("", _("All"))):
            self.gp_status.addItem(v, k)
        self.gp_status.currentIndexChanged.connect(self.load_gate_passes)
        bar.addWidget(self.gp_search, 1)
        bar.addWidget(self.gp_status)
        new = button("New gate pass", "Primary", "plus")
        new.clicked.connect(self.new_gp)
        imp = button("Import CSV / Excel", icon_name="upload")
        imp.clicked.connect(self.import_gp)
        tpl = button("Template", icon_name="download")
        tpl.clicked.connect(self.template)
        edit = button("Edit", icon_name="edit")
        edit.clicked.connect(self.edit_gp)
        canc = button("Cancel gate pass", icon_name="x")
        canc.clicked.connect(self.cancel_gp)
        self.del_gp_btn = button("Delete", icon_name="x")
        self.del_gp_btn.clicked.connect(self.delete_gp)
        for b in (edit, canc, self.del_gp_btn, tpl, imp, new):
            bar.addWidget(b)
        gl.addLayout(bar)
        self.gp_table = make_table(["Gate pass", "Vehicle", "Customer", "Destination", "Products", "Total", "Status",
                                    "Source", "Created"], 4)
        self.gp_table.doubleClicked.connect(self.edit_gp)
        gl.addWidget(self.gp_table)
        self.tabs.addTab(gp, _("Gate passes"))
        # -------- today's sessions
        ss = QWidget()
        sl = QVBoxLayout(ss)
        sl.setContentsMargins(0, 12, 0, 0)
        sb = QHBoxLayout()
        sb.addStretch(1)
        op = button("Open details", icon_name="search")
        op.clicked.connect(self.open_session)
        sb.addWidget(op)
        sl.addLayout(sb)
        self.s_table = make_table(["#", "Started", "Bay", "Gate pass", "Vehicle", "Counted", "Expected", "Status"], 3)
        self.s_table.doubleClicked.connect(self.open_session)
        sl.addWidget(self.s_table)
        self.tabs.addTab(ss, _("Today's sessions"))
        # -------- review queue
        rq = QWidget()
        rl = QVBoxLayout(rq)
        rl.setContentsMargins(0, 12, 0, 0)
        rb = QHBoxLayout()
        rb.addStretch(1)
        rv = button("Review selected session", "Accent", "shield")
        rv.clicked.connect(self.review)
        rb.addWidget(rv)
        rl.addLayout(rb)
        self.r_table = make_table(["Session", "Bay", "Gate pass", "Counts to review", "Oldest"], 2)
        self.r_table.doubleClicked.connect(self.review)
        rl.addWidget(self.r_table)
        self.tabs.addTab(rq, _("Review queue"))
        self.tabs.currentChanged.connect(lambda _i: self.refresh())

    def showEvent(self, e):
        super().showEvent(e)
        self.del_gp_btn.setVisible(bool(self.app.user and self.app.user.can("delete_records")))
        self.refresh()

    def refresh(self):
        i = self.tabs.currentIndex()
        if i == 0:
            self.load_gate_passes()
        elif i == 1:
            self.load_sessions()
        else:
            self.load_review()
        self.tabs.setTabText(2, f"{_('Review queue')} ({self._pending_total()})")

    def _pending_total(self):
        return self.app.db.scalar("SELECT COUNT(*) FROM count_events e JOIN sessions s ON s.id=e.session_id "
                                  "WHERE e.review='pending' AND s.deleted=0") or 0

    # ------------------------------------------------------------- gate passes
    def load_gate_passes(self):
        st = tuple(s for s in (self.gp_status.currentData() or "").split(",") if s)
        gps = self.app.gate_passes.list(st, self.gp_search.text().strip())
        colors = {}
        rows = []
        for i, g in enumerate(gps):
            rows.append([g.number, g.vehicle_no, g.customer, g.destination,
                         ", ".join(f"{it.product_name} × {it.expected_qty}" for it in g.items), g.total_expected,
                         g.status, g.source, time.strftime("%d-%b %H:%M", time.localtime(g.created_at))])
            colors[(i, 6)] = {"open": theme.c("info"), "loading": theme.c("accent"),
                              "completed": theme.c("success"), "cancelled": theme.c("muted")}[g.status]
        fill_table(self.gp_table, rows, [g.id for g in gps], colors)

    def new_gp(self):
        if GatePassDialog(self, self.app).exec():
            self.load_gate_passes()

    def edit_gp(self):
        gid = selected_data(self.gp_table)
        if not gid:
            return
        gp = self.app.gate_passes.get(gid)
        if gp.status not in ("open", "loading"):
            error(self, _("Only open or loading gate passes can be edited."))
            return
        if GatePassDialog(self, self.app, gp).exec():
            self.load_gate_passes()

    def cancel_gp(self):
        gid = selected_data(self.gp_table)
        if not gid:
            return
        gp = self.app.gate_passes.get(gid)
        if gp.status != "open":
            error(self, _("Only open gate passes (not loading) can be cancelled."))
            return
        if confirm(self, f"{_('Cancel gate pass')} {gp.number}?"):
            self.app.gate_passes.set_status(gid, "cancelled", self.app.user)
            self.load_gate_passes()

    def delete_gp(self):
        gid = selected_data(self.gp_table)
        if not gid:
            error(self, _("Select a gate pass first."))
            return
        gp = self.app.gate_passes.get(gid)
        if not confirm(self, f"{_('Delete gate pass')} {gp.number}?"):
            return
        sup, reason = ask_supervisor(self, self.app, _("Admin approval required to delete a gate pass."),
                                     need_reason=True)
        if not sup:
            return
        try:
            self.app.gate_passes.delete(sup, gid, reason)
        except ValueError as e:
            error(self, str(e))
            return
        self.load_gate_passes()

    def import_gp(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Import gate passes"), "", "CSV / Excel (*.csv *.xlsx)")
        if not p:
            return
        n, errs = self.app.gate_passes.import_file(self.app.user, p)
        msg = f"{n} {_('gate pass(es) imported.')}"
        if errs:
            msg += "\n\n" + _("Problems:") + "\n" + "\n".join(errs[:20]) + (f"\n… +{len(errs) - 20}" if len(errs) > 20 else "")
        info(self, msg)
        self.load_gate_passes()

    def template(self):
        p, _f = QFileDialog.getSaveFileName(self, _("Save template"), "gate_pass_template.csv", "CSV (*.csv)")
        if p:
            write_import_template(p)
            open_file(p)

    # ------------------------------------------------------------- sessions
    def load_sessions(self):
        t0, t1 = day_bounds(__import__("datetime").date.today())
        rows = self.app.sessions.search(t0, t1)
        out, colors = [], {}
        for i, r in enumerate(rows):
            res = json.loads(r["result"] or "{}")
            if r["status"] == "active":
                s = self.app.sessions.summary(r["id"])
                counted, expected = s.total_counted, s.total_expected if s.gate_pass else "-"
            else:
                counted, expected = res.get("total_counted", ""), res.get("total_expected", "")
            out.append([r["id"], time.strftime("%H:%M", time.localtime(r["started_at"])), r["bay"], r["gate_pass"] or "-",
                        r["plate_text"] or "-", counted, expected, STATUS_LABEL.get(r["status"], r["status"])])
            colors[(i, 7)] = {"cleared": theme.c("success"), "mismatch": theme.c("danger"), "released": "#9A6511",
                              "active": theme.c("info")}.get(r["status"], theme.c("muted"))
        fill_table(self.s_table, out, [r["id"] for r in rows], colors)

    def open_session(self):
        sid = selected_data(self.s_table)
        if sid:
            from nomload.ui.pages.history import SessionDetailDialog
            SessionDetailDialog(self, self.app, sid, self.main).exec()
            self.refresh()

    # ------------------------------------------------------------- review
    def load_review(self):
        rows = self.app.db.q("SELECT s.id, b.name bay, g.number gp, COUNT(e.id) n, MIN(e.ts) oldest FROM count_events e "
                             "JOIN sessions s ON s.id=e.session_id JOIN bays b ON b.id=s.bay_id "
                             "LEFT JOIN gate_passes g ON g.id=s.gate_pass_id WHERE e.review='pending' AND s.deleted=0 "
                             "GROUP BY s.id ORDER BY oldest")
        fill_table(self.r_table, [[r["id"], r["bay"], r["gp"] or "-", r["n"],
                                   time.strftime("%d-%b %H:%M", time.localtime(r["oldest"]))] for r in rows],
                   [r["id"] for r in rows])

    def review(self):
        sid = selected_data(self.r_table)
        if not sid:
            return
        sup, _r = ask_supervisor(self, self.app, _("Review low-confidence counts"))
        if sup:
            ReviewDialog(self, self.app, sid, sup).exec()
            self.refresh()

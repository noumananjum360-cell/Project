"""History: search past sessions; session details with evidence."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from nomload import theme
from nomload.i18n import _
from nomload.services import evidence
from nomload.services.reports import STATUS_LABEL, fmt_dur, fmt_ts
from nomload.ui.dialogs import ReviewDialog, SessionResultDialog, ask_supervisor
from nomload.ui.pages.common import open_file, open_folder, report_path
from nomload.ui.widgets import (Card, PageHeader, button, confirm, error, fill_table, fit_to_screen, info, make_table,
                                run_async, selected_data)


def status_color(s: str) -> str:
    return {"cleared": theme.c("success"), "mismatch": theme.c("danger"), "released": "#9A6511",
            "active": theme.c("info")}.get(s, theme.c("muted"))


class HistoryPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(PageHeader("History"))
        f = QHBoxLayout()
        self.d0 = QDateEdit(QDate.currentDate().addDays(-7))
        self.d1 = QDateEdit(QDate.currentDate())
        for d in (self.d0, self.d1):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MMM-yyyy")
        self.plate = QLineEdit()
        self.plate.setPlaceholderText(_("Plate"))
        self.gp = QLineEdit()
        self.gp.setPlaceholderText(_("Gate pass no."))
        self.product = QComboBox()
        self.bay = QComboBox()
        self.status = QComboBox()
        for k, v in (("", _("Any status")), ("cleared", _("Cleared")), ("mismatch", _("Mismatch")),
                     ("released", _("Released")), ("active", _("Loading")), ("cancelled", _("Cancelled"))):
            self.status.addItem(v, k)
        go = button("Search", "Primary", "search")
        go.clicked.connect(self.search)
        for w, lbl in ((self.d0, "From"), (self.d1, "To")):
            l = QLabel(_(lbl))
            l.setObjectName("Muted")
            f.addWidget(l)
            f.addWidget(w)
        for w in (self.plate, self.gp, self.product, self.bay, self.status, go):
            f.addWidget(w)
        lay.addLayout(f)
        self.table = make_table(["#", "Date / time", "Bay", "Gate pass", "Customer", "Vehicle", "Expected", "Counted",
                                 "Status"], 4)
        self.table.doubleClicked.connect(self.open)
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        lay.addWidget(self.table, 1)
        bb = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("Muted")
        bb.addWidget(self.count_lbl)
        bb.addStretch(1)
        self.del_btn = button("Delete selected", icon_name="x")
        self.del_btn.clicked.connect(self.delete_selected)
        bb.addWidget(self.del_btn)
        op = button("Open details", "Primary", "search")
        op.clicked.connect(self.open)
        bb.addWidget(op)
        lay.addLayout(bb)
        for e in (self.plate, self.gp):
            e.returnPressed.connect(self.search)

    def showEvent(self, e):
        super().showEvent(e)
        self.del_btn.setVisible(bool(self.app.user and self.app.user.can("delete_records")))
        cur_p, cur_b = self.product.currentData(), self.bay.currentData()
        self.product.clear()
        self.product.addItem(_("Any product"), None)
        for p in self.app.products.list():
            self.product.addItem(p.name, p.id)
        self.bay.clear()
        self.bay.addItem(_("Any bay"), None)
        for b in self.app.bays.list():
            self.bay.addItem(b.name, b.id)
        if cur_p:
            self.product.setCurrentIndex(max(0, self.product.findData(cur_p)))
        if cur_b:
            self.bay.setCurrentIndex(max(0, self.bay.findData(cur_b)))
        self.search()

    def search(self):
        t0 = time.mktime(self.d0.date().toPython().timetuple())
        t1 = time.mktime((self.d1.date().toPython() + dt.timedelta(days=1)).timetuple())
        rows = self.app.sessions.search(t0, t1, self.plate.text().strip(), self.gp.text().strip(),
                                        self.product.currentData(), self.bay.currentData(), self.status.currentData() or "")
        out, colors = [], {}
        for i, r in enumerate(rows):
            res = json.loads(r["result"] or "{}")
            out.append([r["id"], fmt_ts(r["started_at"])[:17], r["bay"], r["gate_pass"] or "-", r["customer"] or "",
                        r["plate_text"] or "-", res.get("total_expected", ""), res.get("total_counted", ""),
                        STATUS_LABEL.get(r["status"], r["status"])])
            colors[(i, 8)] = status_color(r["status"])
        fill_table(self.table, out, [r["id"] for r in rows], colors)
        self.count_lbl.setText(f"{len(rows)} {_('session(s)')}")

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        sids = [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]
        if not sids:
            error(self, _("Select one or more sessions first."))
            return
        if not confirm(self, f"{_('Delete')} {len(sids)} {_('session(s) from History?')}"):
            return
        sup, reason = ask_supervisor(self, self.app, _("Admin approval required to delete records."), need_reason=True)
        if not sup:
            return
        if not sup.can("delete_records"):
            error(self, _("Only an Admin can delete records."))
            return
        skipped = 0
        for sid in sids:
            try:
                self.app.sessions.soft_delete(sid, sup, reason)
            except Exception:
                skipped += 1
        if skipped:
            error(self, f"{skipped} {_('session(s) are still loading and were not deleted.')}")
        self.search()

    def open(self):
        sid = selected_data(self.table)
        if sid:
            SessionDetailDialog(self, self.app, sid, self.main).exec()
            self.search()


class SessionDetailDialog(QDialog):
    def __init__(self, parent, app, sid: int, main=None):
        super().__init__(parent)
        self.app = app
        self.sid = sid
        self.main = main
        self.setWindowTitle(f"{_('Session')} #{sid}")
        fit_to_screen(self, 1100, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        self.head = QLabel()
        self.head.setStyleSheet("font-size: 20px; font-weight: 700;")
        lay.addWidget(self.head)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        # summary tab
        sw = QWidget()
        sl = QHBoxLayout(sw)
        left = QVBoxLayout()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        left.addWidget(self.info)
        self.lines = make_table(["Product", "Expected", "Counted", "Difference", "Tolerance", "To review", "Result"], 0)
        left.addWidget(self.lines, 1)
        sl.addLayout(left, 2)
        right = QVBoxLayout()
        self.plate_img = QLabel()
        self.plate_img.setMinimumWidth(260)
        right.addWidget(self.plate_img)
        right.addStretch(1)
        sl.addLayout(right, 1)
        self.tabs.addTab(sw, _("Summary"))
        # snapshots
        self.snaps = QListWidget()
        self.snaps.setViewMode(QListWidget.ViewMode.IconMode)
        self.snaps.setIconSize(QSize(240, 140))
        self.snaps.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.snaps.setSpacing(8)
        self.snaps.itemDoubleClicked.connect(lambda it: open_file(it.data(Qt.ItemDataRole.UserRole)))
        self.tabs.addTab(self.snaps, _("Item snapshots"))
        # events
        self.events = make_table(["Time", "Product", "Class", "Dir", "Units", "Confidence", "Review", "Reason"], 7)
        self.tabs.addTab(self.events, _("Count events"))
        # evidence
        self.ev = make_table(["Type", "File", "SHA-256", "Integrity"], 1)
        self.tabs.addTab(self.ev, _("Evidence"))
        # audit
        self.audit = make_table(["Time", "User", "Action", "Details"], 3)
        self.tabs.addTab(self.audit, _("Audit trail"))
        # buttons
        bb = QHBoxLayout()
        self.b_clip = button("Play clip", icon_name="film")
        self.b_clip.clicked.connect(self.play)
        self.b_verify = button("Verify evidence", icon_name="shield")
        self.b_verify.clicked.connect(self.verify)
        self.b_pack = button("Evidence pack", icon_name="download")
        self.b_pack.clicked.connect(self.pack)
        self.b_cert = button("Loading certificate", icon_name="reports")
        self.b_cert.clicked.connect(self.cert)
        for b in (self.b_clip, self.b_verify, self.b_pack, self.b_cert):
            bb.addWidget(b)
        bb.addStretch(1)
        self.b_review = button("Review", "Accent", "shield")
        self.b_review.clicked.connect(self.review)
        self.b_adjust = button("Adjust count", icon_name="edit")
        self.b_adjust.clicked.connect(self.adjust)
        self.b_release = button("Supervisor release", "Danger", "key")
        self.b_release.clicked.connect(self.release)
        self.b_delete = button("Delete")
        self.b_delete.clicked.connect(self.delete)
        for b in (self.b_review, self.b_adjust, self.b_release, self.b_delete):
            bb.addWidget(b)
        close = button("Close")
        close.clicked.connect(self.accept)
        bb.addWidget(close)
        lay.addLayout(bb)
        self.load()

    def load(self):
        s = self.app.sessions.summary(self.sid)
        self.s = s
        col = status_color(s.status)
        self.head.setText(f"{_('Session')} #{s.id} · {s.bay_name} · <span style='color:{col}'>"
                          f"{STATUS_LABEL.get(s.status, s.status)}</span>")
        gp = s.gate_pass
        rows = [(_("Gate pass"), gp.number if gp else "-"), (_("Customer"), gp.customer if gp else "-"),
                (_("Destination"), gp.destination if gp else "-"), (_("Vehicle on gate pass"), gp.vehicle_no if gp else "-"),
                (_("Plate read"), f"{s.plate_text or '-'}" + (f" ({s.plate_confidence:.0%})" if s.plate_confidence else "")),
                (_("Started"), fmt_ts(s.started_at) + (f" · {s.started_by}" if s.started_by else "")),
                (_("Finished"), fmt_ts(s.ended_at) + (f" · {s.closed_by}" if s.closed_by else "")),
                (_("Loading time"), fmt_dur(s.duration_s))]
        if s.status == "released":
            rows += [(_("Released by"), s.released_by), (_("Reason"), s.release_reason)]
        self.info.setText("<table cellpadding='3'>" + "".join(
            f"<tr><td style='color:{theme.c('muted')}'>{k}</td><td><b>{v}</b></td></tr>" for k, v in rows) + "</table>")
        out, colors = [], {}
        for i, l in enumerate(s.lines):
            out.append([l.name, "-" if l.expected is None else l.expected, l.counted,
                        f"{l.diff:+d}" if l.expected is not None else "-", f"±{l.allowed}", l.pending,
                        "OK" if l.ok else "MISMATCH"])
            colors[(i, 6)] = theme.c("success") if l.ok else theme.c("danger")
        fill_table(self.lines, out, colors=colors)
        if s.plate_image and Path(s.plate_image).exists():
            self.plate_img.setPixmap(QPixmap(s.plate_image).scaledToWidth(260, Qt.TransformationMode.SmoothTransformation))
        evs = self.app.sessions.events(self.sid)
        self.snaps.clear()
        for e in evs:
            if e["snapshot"] and Path(e["snapshot"]).exists():
                it = QListWidgetItem(QIcon(e["snapshot"]), f"{'+1' if e['direction'] > 0 else '-1'} {e['product'] or e['cls']}"
                                     f"  {e['confidence']:.0%}  {time.strftime('%H:%M:%S', time.localtime(e['ts']))}")
                it.setData(Qt.ItemDataRole.UserRole, e["snapshot"])
                self.snaps.addItem(it)
        fill_table(self.events, [[time.strftime("%H:%M:%S", time.localtime(e["ts"])), e["product"] or "-", e["cls"],
                                  "+1" if e["direction"] > 0 else "-1", e["units"], f"{e['confidence']:.0%}", e["review"],
                                  e["reason"]] for e in evs])
        self.tabs.setTabText(1, f"{_('Item snapshots')} ({self.snaps.count()})")
        fill_table(self.ev, [[r["kind"], Path(r["path"]).name, r["sha256"][:24] + "…", ""] for r in self.app.db.q(
            "SELECT * FROM evidence_files WHERE session_id=? ORDER BY id", (self.sid,))])
        au = self.app.db.q("SELECT * FROM audit_log WHERE (entity='session' AND entity_id=?) OR "
                           "(entity='count_event' AND details LIKE ?) ORDER BY ts", (str(self.sid), f'%"session": {self.sid}%'))
        fill_table(self.audit, [[fmt_ts(a["ts"]), a["username"], a["action"], a["details"][:200]] for a in au])
        u = self.app.user
        self.b_clip.setEnabled(bool(s.clip_path and Path(s.clip_path).exists()))
        self.b_release.setVisible(s.status == "mismatch")
        self.b_review.setVisible(s.total_pending > 0)
        self.b_adjust.setVisible(s.status in ("active", "mismatch"))
        self.b_delete.setVisible(bool(u and u.can("delete_records")))

    def play(self):
        if self.s.clip_path:
            open_file(self.s.clip_path)

    def verify(self):
        run_async(self, lambda: evidence.verify_session(self.app.db, self.sid), self._verified,
                  busy=_("Checking evidence files (SHA-256)..."))

    def _verified(self, res):
        rows, colors = [], {}
        for i, r in enumerate(res):
            rows.append([r["kind"], Path(r["path"]).name, r["sha256"][:24] + "…", r["status"].upper()])
            colors[(i, 3)] = theme.c("success") if r["status"] == "ok" else (
                theme.c("muted") if r["status"] == "removed" else theme.c("danger"))
        fill_table(self.ev, rows, colors=colors)
        self.tabs.setCurrentWidget(self.ev)
        bad = [r for r in res if r["status"] not in ("ok", "removed")]
        from nomload.services.context import audit
        audit(self.app.db, self.app.user, "evidence_verified", "session", self.sid, {"files": len(res), "problems": len(bad)})
        if bad:
            error(self, f"{len(bad)} {_('evidence file(s) are MISSING or MODIFIED since recording.')}")
        else:
            info(self, f"{_('All')} {len(res)} {_('evidence files are intact (SHA-256 verified).')}")

    def pack(self):
        default = str(Path.home() / f"NomLoad_evidence_session_{self.sid}.zip")
        p, _f = QFileDialog.getSaveFileName(self, _("Save evidence pack"), default, "ZIP (*.zip)")
        if not p:
            return
        pdf = report_path(f"certificate_session_{self.sid}.pdf")

        def work():
            self.app.reports.loading_certificate(self.sid, pdf)
            return evidence.build_evidence_pack(self.app.db, self.sid, p, pdf)

        def done(_r):
            from nomload.services.context import audit
            audit(self.app.db, self.app.user, "evidence_pack_exported", "session", self.sid, {"path": p})
            open_folder(p)

        run_async(self, work, done, busy=_("Building evidence pack..."))

    def cert(self):
        p = report_path(f"certificate_session_{self.sid}.pdf")
        run_async(self, lambda: self.app.reports.loading_certificate(self.sid, p), lambda _r: open_file(p),
                  busy=_("Creating certificate..."))

    def review(self):
        sup, _r = ask_supervisor(self, self.app, _("Review low-confidence counts"))
        if sup:
            ReviewDialog(self, self.app, self.sid, sup).exec()
            self.load()

    def adjust(self):
        from PySide6.QtWidgets import QFormLayout
        from nomload.ui.dialogs import Base
        d = Base(self, "Adjust count", 460)
        f = QFormLayout()
        prod = QComboBox()
        for l in self.s.lines:
            if l.product_id:
                prod.addItem(l.name, l.product_id)
        if prod.count() == 0:
            for p in self.app.products.list(active_only=True):
                prod.addItem(p.name, p.id)
        delta = QSpinBox()
        delta.setRange(-1000, 1000)
        f.addRow(_("Product"), prod)
        f.addRow(_("Add / remove units"), delta)
        d.lay.addLayout(f)
        d.buttons("Continue")
        if not d.exec() or delta.value() == 0:
            return
        sup, reason = ask_supervisor(self, self.app, f"{_('Adjust')} {prod.currentText()} {_('by')} {delta.value():+d}?",
                                     need_reason=True)
        if sup:
            try:
                self.app.sessions.manual_adjust(self.sid, prod.currentData(), delta.value(), sup, reason)
            except Exception as e:
                error(self, str(e))
            self.load()

    def release(self):
        d = SessionResultDialog(self, self.app, self.s, self.main.sound if self.main else None)
        d.exec()
        self.load()

    def delete(self):
        if not confirm(self, _("Delete this session from history? It stays in the audit log and evidence store.")):
            return
        sup, reason = ask_supervisor(self, self.app, _("Admin confirmation required to delete a record."), need_reason=True)
        if sup and sup.can("delete_records"):
            self.app.sessions.soft_delete(self.sid, sup, reason)
            self.accept()
        elif sup:
            error(self, _("Only an Admin can delete records."))

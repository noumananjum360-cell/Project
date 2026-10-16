"""Dialogs used across pages."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox,
                               QTableWidget, QVBoxLayout, QWidget)

from nomload import theme
from nomload.i18n import _
from nomload.services.context import ROLE_LABELS, AuthError, User
from nomload.ui.widgets import button, error, fill_table, make_table


class Base(QDialog):
    """Dialog with a scrollable body and a footer that always stays visible.

    Content is added to ``self.lay`` (inside a scroll area); ``buttons()`` puts
    Cancel/OK in the fixed footer, so Save is reachable even on small screens.
    """

    def __init__(self, parent, title: str, width: int = 520):
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea
        self.setWindowTitle(_(title))
        self.setMinimumWidth(min(width, 900))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("DialogBody")
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(22, 20, 22, 10)
        self.lay.setSpacing(12)
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)
        foot = QFrame()
        foot.setObjectName("DialogFooter")
        foot.setStyleSheet(f"#DialogFooter {{ border-top: 1px solid {theme.c('border')}; }}")
        self.footer = QHBoxLayout(foot)
        self.footer.setContentsMargins(22, 12, 22, 14)
        outer.addWidget(foot)
        self._foot = foot
        t = QLabel(_(title))
        t.setObjectName("CardTitle")
        t.setStyleSheet("font-size: 20px;")
        self.lay.addWidget(t)

    def showEvent(self, e):
        super().showEvent(e)
        if self._foot.layout().count() == 0:
            self._foot.hide()
        # open at the natural size, but never taller/wider than the screen (the body scrolls instead)
        from PySide6.QtGui import QGuiApplication
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        body = self._scroll.widget().sizeHint()
        want_h = body.height() + (self._foot.sizeHint().height() if self._foot.isVisible() else 0) + 8
        h = min(max(self.height(), want_h), int(scr.height() * 0.9))
        w = min(max(self.width(), body.width() + 24), int(scr.width() * 0.92))
        self.resize(w, h)
        g = self.frameGeometry()
        g.moveCenter(scr.center())
        self.move(g.topLeft())

    def buttons(self, ok_text="OK", ok_kind="Primary"):
        cancel = button("Cancel")
        ok = button(ok_text, ok_kind)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        ok.setDefault(True)
        self.footer.addStretch(1)
        self.footer.addWidget(cancel)
        self.footer.addWidget(ok)
        self.ok_btn = ok
        return ok

    def _accept(self):
        self.accept()


# ----------------------------------------------------------------- supervisor approval
class SupervisorDialog(Base):
    """Supervisor username + PIN (+ optional written reason)."""

    def __init__(self, parent, app, action: str, need_reason: bool = False, reason_hint: str = ""):
        super().__init__(parent, "Supervisor approval", 480)
        self.app = app
        self.need_reason = need_reason
        msg = QLabel(_(action))
        msg.setWordWrap(True)
        self.lay.addWidget(msg)
        f = QFormLayout()
        self.user = QComboBox()
        self.user.setEditable(True)
        for r in app.db.q("SELECT username FROM users WHERE role IN ('admin','supervisor') AND active=1 ORDER BY username"):
            self.user.addItem(r["username"])
        if app.user and app.user.role in ("admin", "supervisor"):
            self.user.setCurrentText(app.user.username)
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText("PIN")
        self.pin.setMaxLength(12)
        f.addRow(_("Supervisor"), self.user)
        f.addRow(_("PIN"), self.pin)
        self.reason = QPlainTextEdit()
        self.reason.setPlaceholderText(reason_hint or _("Write the reason (required)"))
        self.reason.setFixedHeight(90)
        if need_reason:
            f.addRow(_("Reason"), self.reason)
        self.lay.addLayout(f)
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{theme.c('danger')};")
        self.lay.addWidget(self.err)
        self.buttons("Approve")
        self.supervisor: User | None = None
        self.pin.setFocus()

    def _accept(self):
        if self.need_reason and len(self.reason.toPlainText().strip()) < 5:
            self.err.setText(_("Please write a clear reason (at least 5 characters)."))
            return
        try:
            self.supervisor = self.app.auth.verify_supervisor(self.user.currentText().strip(), self.pin.text())
        except AuthError as e:
            self.err.setText(str(e))
            self.pin.clear()
            return
        self.accept()

    @property
    def reason_text(self) -> str:
        return self.reason.toPlainText().strip()


def ask_supervisor(parent, app, action: str, need_reason=False, reason_hint="") -> tuple[User | None, str]:
    d = SupervisorDialog(parent, app, action, need_reason, reason_hint)
    if d.exec() == QDialog.DialogCode.Accepted:
        return d.supervisor, d.reason_text
    return None, ""


# ----------------------------------------------------------------- gate passes
class GatePassDialog(Base):
    def __init__(self, parent, app, gate_pass=None):
        super().__init__(parent, "Edit gate pass" if gate_pass else "New gate pass", 680)
        self.app = app
        self.gp = gate_pass
        f = QFormLayout()
        self.number = QLineEdit(gate_pass.number if gate_pass else "")
        self.number.setPlaceholderText("e.g. GP-1001 or invoice number")
        self.vehicle = QLineEdit(gate_pass.vehicle_no if gate_pass else "")
        self.vehicle.setPlaceholderText("e.g. LES-4721")
        self.customer = QLineEdit(gate_pass.customer if gate_pass else "")
        self.driver = QLineEdit(gate_pass.driver_name if gate_pass else "")
        self.phone = QLineEdit(gate_pass.driver_phone if gate_pass else "")
        self.dest = QLineEdit(gate_pass.destination if gate_pass else "")
        if gate_pass:
            for w in (self.number, self.customer, self.driver, self.phone, self.dest):
                w.setReadOnly(True)
        f.addRow(_("Gate pass / invoice no."), self.number)
        f.addRow(_("Vehicle number"), self.vehicle)
        f.addRow(_("Customer / distributor"), self.customer)
        f.addRow(_("Driver name"), self.driver)
        f.addRow(_("Driver phone"), self.phone)
        f.addRow(_("Destination"), self.dest)
        self.lay.addLayout(f)
        lbl = QLabel(_("Products and quantities"))
        lbl.setObjectName("CardTitle")
        self.lay.addWidget(lbl)
        self.rows_box = QVBoxLayout()
        self.lay.addLayout(self.rows_box)
        add = button("Add product", icon_name="plus")
        add.clicked.connect(lambda: self._add_row())
        self.lay.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        self.rows: list[tuple[QComboBox, QSpinBox, QWidget]] = []
        if gate_pass:
            for it in gate_pass.items:
                self._add_row(it.product_id, it.expected_qty)
        else:
            self._add_row()
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{theme.c('danger')};")
        self.lay.addWidget(self.err)
        self.buttons("Save")

    def _add_row(self, pid=None, qty=0):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        cb = QComboBox()
        for p in self.app.products.list(active_only=True):
            cb.addItem(f"{p.name}  ({p.detector_class}, x{p.units_per_detection})", p.id)
        if pid:
            i = cb.findData(pid)
            if i >= 0:
                cb.setCurrentIndex(i)
        sp = QSpinBox()
        sp.setRange(0, 100000)
        sp.setValue(qty)
        sp.setSuffix(" " + _("units"))
        sp.setMinimumWidth(140)
        rm = QPushButton("✕")
        rm.setFixedWidth(40)
        h.addWidget(cb, 1)
        h.addWidget(sp)
        h.addWidget(rm)
        row = (cb, sp, w)
        rm.clicked.connect(lambda: self._remove(row))
        self.rows.append(row)
        self.rows_box.addWidget(w)

    def _remove(self, row):
        if len(self.rows) > 1:
            self.rows.remove(row)
            row[2].deleteLater()

    def items(self):
        agg: dict[int, int] = {}
        for cb, sp, _w in self.rows:
            if sp.value() > 0:
                agg[cb.currentData()] = agg.get(cb.currentData(), 0) + sp.value()
        return list(agg.items())

    def _accept(self):
        try:
            if self.gp:
                self.app.gate_passes.update_items(self.app.user, self.gp.id, self.items(), self.vehicle.text())
            else:
                self.created_id = self.app.gate_passes.create(
                    self.app.user, self.number.text(), self.items(), self.vehicle.text(), self.customer.text(),
                    self.driver.text(), self.phone.text(), self.dest.text())
        except Exception as e:
            self.err.setText(str(e))
            return
        self.accept()


class GatePassPicker(Base):
    """Choose the gate pass for a new loading session."""

    def __init__(self, parent, app, plate_hint: str = ""):
        super().__init__(parent, "Start loading", 760)
        self.app = app
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search gate pass, vehicle or customer"))
        self.search.textChanged.connect(self.reload)
        new = button("New gate pass", icon_name="plus")
        new.clicked.connect(self._new)
        top.addWidget(self.search, 1)
        top.addWidget(new)
        self.lay.addLayout(top)
        self.table = make_table(["Gate pass", "Vehicle", "Customer", "Products", "Total"], 3)
        self.table.setMinimumHeight(300)
        self.table.doubleClicked.connect(self._accept)
        self.lay.addWidget(self.table)
        self.none_btn = button("Start without gate pass")
        self.none_btn.setToolTip(_("Counts will be recorded; link a gate pass before closing."))
        self.none_btn.clicked.connect(self._without)
        bb = QHBoxLayout()
        bb.addWidget(self.none_btn)
        bb.addStretch(1)
        c = button("Cancel")
        c.clicked.connect(self.reject)
        ok = button("Start loading", "Primary", "play")
        ok.clicked.connect(self._accept)
        bb.addWidget(c)
        bb.addWidget(ok)
        self.footer.addLayout(bb)
        self.gate_pass_id: int | None = None
        self.search.setText(plate_hint)
        self.reload()

    def reload(self):
        gps = self.app.gate_passes.list(("open",), self.search.text().strip())
        fill_table(self.table, [[g.number, g.vehicle_no, g.customer, ", ".join(f"{i.product_name} {i.expected_qty}"
                                                                            for i in g.items), g.total_expected]
                                for g in gps], [g.id for g in gps])
        if gps:
            self.table.selectRow(0)

    def _new(self):
        d = GatePassDialog(self, self.app)
        if d.exec():
            self.gate_pass_id = getattr(d, "created_id", None)
            self.accept()

    def _without(self):
        self.gate_pass_id = None
        self.accept()

    def _accept(self):
        r = self.table.currentRow()
        if r < 0:
            error(self, _("Select a gate pass first."))
            return
        self.gate_pass_id = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
        self.accept()


# ----------------------------------------------------------------- plate
class PlateDialog(Base):
    def __init__(self, parent, current: str = "", image: str | None = None):
        super().__init__(parent, "Correct number plate", 460)
        if image and Path(image).exists():
            l = QLabel()
            l.setPixmap(QPixmap(image).scaledToWidth(380, Qt.TransformationMode.SmoothTransformation))
            self.lay.addWidget(l)
        self.edit = QLineEdit(current)
        self.edit.setPlaceholderText("LES-4721")
        self.edit.setStyleSheet("font-size: 26px; font-weight: 700; font-family: Consolas, monospace;")
        self.lay.addWidget(self.edit)
        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        self.lay.addWidget(self.hint)
        self.edit.textChanged.connect(self._hint)
        self.buttons("Save plate")
        self._hint()

    def _hint(self):
        from nomload.core.plate_formats import parse
        p = parse(self.edit.text())
        self.hint.setText(f"{_('Will be saved as')}: {p.text or '-'}   ({_('province')}: {p.province})")

    @property
    def text(self) -> str:
        from nomload.core.plate_formats import parse
        return parse(self.edit.text()).text or self.edit.text().strip().upper()


# ----------------------------------------------------------------- review
class ReviewDialog(Base):
    """Supervisor review of low-confidence counts with snapshots."""

    def __init__(self, parent, app, session_id: int, supervisor: User):
        super().__init__(parent, "Review low-confidence counts", 600)
        from nomload.ui.widgets import fit_to_screen
        fit_to_screen(self, 980, 720)
        self.app = app
        self.sid = session_id
        self.sup = supervisor
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(260, 150))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setSpacing(10)
        self.list.setMinimumHeight(420)
        self.lay.addWidget(self.list)
        row = QHBoxLayout()
        self.product = QComboBox()
        self.product.addItem(_("(keep product)"), None)
        for p in app.products.list(active_only=True):
            self.product.addItem(p.name, p.id)
        acc = button("Accept selected", "Success", "check")
        rej = button("Reject selected", "Danger", "x")
        acc_all = button("Accept all")
        acc.clicked.connect(lambda: self._apply(True))
        rej.clicked.connect(lambda: self._apply(False))
        acc_all.clicked.connect(self._accept_all)
        row.addWidget(QLabel(_("Product")))
        row.addWidget(self.product, 1)
        row.addWidget(acc_all)
        row.addWidget(rej)
        row.addWidget(acc)
        self.lay.addLayout(row)
        done = button("Done", "Primary")
        done.clicked.connect(self.accept)
        self.lay.addWidget(done, alignment=Qt.AlignmentFlag.AlignRight)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.reload()

    def reload(self):
        from PySide6.QtGui import QIcon
        self.list.clear()
        for e in self.app.sessions.pending_events(self.sid):
            sign = "+1" if e["direction"] > 0 else "-1"
            it = QListWidgetItem(f"#{e['id']} {e['cls']} {sign}  {e['confidence']:.0%}\n{e['reason']}\n"
                                 f"{time.strftime('%H:%M:%S', time.localtime(e['ts']))} → {e['product'] or '-'}")
            if e["snapshot"] and Path(e["snapshot"]).exists():
                it.setIcon(QIcon(e["snapshot"]))
            it.setData(Qt.ItemDataRole.UserRole, e["id"])
            self.list.addItem(it)
        if self.list.count() == 0:
            self.list.addItem(_("Nothing to review."))

    def _apply(self, accept: bool):
        ids = [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems() if i.data(Qt.ItemDataRole.UserRole)]
        for eid in ids:
            self.app.sessions.review_event(eid, accept, self.sup, self.product.currentData() if accept else None)
        self.reload()

    def _accept_all(self):
        self.list.selectAll()
        self._apply(True)


# ----------------------------------------------------------------- result
class SessionResultDialog(QDialog):
    """Big CLEARED / MISMATCH screen shown when a session is closed."""

    def __init__(self, parent, app, summary, sound=None):
        super().__init__(parent)
        self.app = app
        self.s = summary
        self.sound = sound
        self.setWindowTitle(_("Loading result"))
        self.setMinimumWidth(720)
        ok = summary.status == "cleared"
        color = theme.c("success") if ok else theme.c("danger")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 16)
        banner = QLabel(_("CLEARED") if ok else _("MISMATCH"))
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet(f"background:{color}; color:white; font-size:54px; font-weight:800; padding:26px;")
        lay.addWidget(banner)
        sub = QLabel((_("Quantity matches. Truck may leave.") if ok else
                      _("Quantity does not match. Supervisor approval required.")))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 17px; padding: 10px 20px;")
        lay.addWidget(sub)
        info = QLabel(f"<b>{_('Truck')}:</b> {summary.plate_text or '-'} &nbsp; <b>{_('Gate pass')}:</b> "
                      f"{summary.gate_pass.number if summary.gate_pass else '-'} &nbsp; <b>{_('Bay')}:</b> {summary.bay_name}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(info)
        t = make_table(["Product", "Expected", "Counted", "Difference", "To review", "Result"], 0)
        rows, colors = [], {}
        for i, l in enumerate(summary.lines):
            rows.append([l.name, "-" if l.expected is None else l.expected, l.counted,
                         f"{l.diff:+d}" if l.expected is not None else "-", l.pending, "OK" if l.ok else "MISMATCH"])
            colors[(i, 5)] = theme.c("success") if l.ok else theme.c("danger")
        fill_table(t, rows, colors=colors)
        t.setMinimumHeight(min(320, 60 + 40 * len(rows)))
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(20, 6, 20, 6)
        wl.addWidget(t)
        lay.addWidget(w)
        bb = QHBoxLayout()
        bb.setContentsMargins(20, 0, 20, 0)
        cert = button("Loading certificate", icon_name="reports")
        cert.clicked.connect(self._certificate)
        bb.addWidget(cert)
        bb.addStretch(1)
        if not ok:
            if summary.total_pending:
                rev = button(f"{_('Review')} ({summary.total_pending})", "Accent", "shield")
                rev.clicked.connect(self._review)
                bb.addWidget(rev)
            rel = button("Supervisor release", "Danger", "key", big=True)
            rel.clicked.connect(self._release)
            bb.addWidget(rel)
            hold = button("Keep truck on hold", big=True)
            hold.clicked.connect(self.accept)
            bb.addWidget(hold)
        else:
            close = button("OK", "Success", "check", big=True)
            close.clicked.connect(self.accept)
            bb.addWidget(close)
        lay.addLayout(bb)
        if not ok and sound:
            sound.start_alarm()

    def done(self, r):
        if self.sound:
            self.sound.stop_alarm()
        super().done(r)

    def _certificate(self):
        from nomload.ui.pages.common import open_file, report_path
        from nomload.ui.widgets import run_async
        p = report_path(f"certificate_session_{self.s.id}.pdf")
        run_async(self, lambda: self.app.reports.loading_certificate(self.s.id, p), lambda _r: open_file(p),
                  busy=_("Creating certificate..."))

    def _review(self):
        if self.sound:
            self.sound.stop_alarm()
        sup, _r = ask_supervisor(self, self.app, _("Review low-confidence counts"))
        if sup:
            ReviewDialog(self, self.app, self.s.id, sup).exec()
            self.s = self.app.sessions.summary(self.s.id)
            # re-evaluate: reviewing may resolve the mismatch
            lines = self.s.lines
            if self.s.gate_pass and lines and all(l.ok for l in lines) and self.s.total_pending == 0:
                self.app.db.execute("UPDATE sessions SET status='cleared' WHERE id=?", (self.s.id,))
                self.app.gate_passes.set_status(self.s.gate_pass.id, "completed", sup)
                from nomload.services.context import audit
                audit(self.app.db, sup, "session_cleared_after_review", "session", self.s.id)
                QDialog.done(self, 1)
                SessionResultDialog(self.parent(), self.app, self.app.sessions.summary(self.s.id), self.sound).exec()

    def _release(self):
        if self.sound:
            self.sound.stop_alarm()
        sup, reason = ask_supervisor(self, self.app, _("Release this truck although the quantity does not match?"),
                                     need_reason=True, reason_hint=_("e.g. 5 bags short - customer informed, added to next trip"))
        if sup:
            try:
                self.app.sessions.release(self.s.id, sup, reason)
                self.app.alerts.raise_alert("session_released", f"Session #{self.s.id} ({self.s.plate_text or '-'}) "
                                            f"released by {sup.display}: {reason}", self.s.bay_id, self.s.id)
            except Exception as e:
                error(self, str(e))
                return
            self.accept()


# ----------------------------------------------------------------- users / password
class ChangePasswordDialog(Base):
    def __init__(self, parent, app, forced: bool = False):
        super().__init__(parent, "Change password", 440)
        self.app = app
        if forced:
            m = QLabel(_("Please set a new password."))
            m.setWordWrap(True)
            self.lay.addWidget(m)
        f = QFormLayout()
        self.old = QLineEdit(); self.old.setEchoMode(QLineEdit.EchoMode.Password)
        self.new = QLineEdit(); self.new.setEchoMode(QLineEdit.EchoMode.Password)
        self.rep = QLineEdit(); self.rep.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow(_("Current password"), self.old)
        f.addRow(_("New password"), self.new)
        f.addRow(_("Repeat new password"), self.rep)
        self.pin = QLineEdit(); self.pin.setEchoMode(QLineEdit.EchoMode.Password); self.pin.setPlaceholderText(_("leave empty to keep"))
        if app.user.role in ("admin", "supervisor"):
            f.addRow(_("New supervisor PIN"), self.pin)
        self.lay.addLayout(f)
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{theme.c('danger')};")
        self.lay.addWidget(self.err)
        self.buttons("Save")

    def _accept(self):
        from nomload.data import crypto
        r = self.app.db.one("SELECT pw_hash FROM users WHERE id=?", (self.app.user.id,))
        if not crypto.verify_secret(self.old.text(), r["pw_hash"]):
            self.err.setText(_("Current password is incorrect."))
            return
        if self.new.text() != self.rep.text():
            self.err.setText(_("New passwords do not match."))
            return
        try:
            self.app.auth.set_password(self.app.user.id, self.new.text(), self.app.user)
            if self.pin.text():
                self.app.auth.set_pin(self.app.user.id, self.pin.text(), self.app.user)
        except AuthError as e:
            self.err.setText(str(e))
            return
        self.app.user.must_change_pw = False
        self.accept()


class UserDialog(Base):
    def __init__(self, parent, app, row=None):
        super().__init__(parent, "Edit user" if row else "New user", 460)
        self.app = app
        self.row = row
        f = QFormLayout()
        self.username = QLineEdit(row["username"] if row else "")
        self.username.setReadOnly(bool(row))
        self.full = QLineEdit(row["full_name"] if row else "")
        self.role = QComboBox()
        for k, v in ROLE_LABELS.items():
            self.role.addItem(v, k)
        if row:
            self.role.setCurrentIndex(self.role.findData(row["role"]))
        self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText(_("leave empty to keep") if row else _("at least 6 characters"))
        self.pin = QLineEdit(); self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText(_("4+ digits, supervisors and admins"))
        f.addRow(_("Username"), self.username)
        f.addRow(_("Full name"), self.full)
        f.addRow(_("Role"), self.role)
        f.addRow(_("Password"), self.pw)
        f.addRow(_("Supervisor PIN"), self.pin)
        self.lay.addLayout(f)
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{theme.c('danger')};")
        self.lay.addWidget(self.err)
        self.buttons("Save")

    def _accept(self):
        a = self.app
        try:
            if self.row:
                a.auth.update_user(self.row["id"], a.user, full_name=self.full.text(), role=self.role.currentData())
                if self.pw.text():
                    a.auth.set_password(self.row["id"], self.pw.text(), a.user, must_change=True)
                if self.pin.text():
                    a.auth.set_pin(self.row["id"], self.pin.text(), a.user)
            else:
                a.auth.create_user(self.username.text(), self.pw.text(), self.role.currentData(), self.full.text(),
                                   self.pin.text(), must_change=True, actor=a.user)
        except Exception as e:
            self.err.setText(str(e))
            return
        self.accept()


class AlertsDialog(Base):
    def __init__(self, parent, app):
        super().__init__(parent, "Alerts", 860)
        self.app = app
        self.t = make_table(["Time", "Type", "Message", "Acknowledged"], 2)
        self.t.setMinimumHeight(420)
        self.lay.addWidget(self.t)
        bb = QHBoxLayout()
        bb.addStretch(1)
        ack = button("Acknowledge all", "Primary", "check")
        ack.clicked.connect(self._ack_all)
        close = button("Close")
        close.clicked.connect(self.accept)
        bb.addWidget(ack)
        bb.addWidget(close)
        self.footer.addLayout(bb)
        self.reload()

    def reload(self):
        rows = self.app.alerts.recent(300)
        colors = {}
        out = []
        for i, r in enumerate(rows):
            out.append([time.strftime("%d-%b %H:%M:%S", time.localtime(r["ts"])), r["kind"], r["message"],
                        "✔" if r["acknowledged_at"] else ""])
            if r["severity"] == "critical":
                colors[(i, 1)] = theme.c("danger")
        fill_table(self.t, out, [r["id"] for r in rows], colors)

    def _ack_all(self):
        for r in self.app.alerts.recent(1000, unacked_only=True):
            self.app.alerts.acknowledge(r["id"], self.app.user)
        self.reload()

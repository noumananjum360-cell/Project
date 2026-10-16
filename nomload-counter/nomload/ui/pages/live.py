"""Live Bays: video + big counter vs expected for every loading bay."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QSizePolicy, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QRadioButton, QVBoxLayout, QWidget)

from nomload import theme
from nomload.i18n import _
from nomload.services.sessions import SessionError
from nomload.ui import icons
from nomload.ui.dialogs import GatePassPicker, PlateDialog, ReviewDialog, SessionResultDialog, ask_supervisor
from nomload.ui.widgets import PageHeader, Pill, VideoView, button, confirm, error, info


def fmt_elapsed(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class BayWidget(QFrame):
    def __init__(self, page, bay):
        super().__init__()
        self.page = page
        self.app = page.app
        self.bay = bay
        self.setObjectName("Bay")
        self.session_id = None
        self.summary = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        # header
        h = QHBoxLayout()
        name = QLabel(bay.name)
        name.setObjectName("CardTitle")
        name.setStyleSheet("font-size: 19px;")
        h.addWidget(name)
        self.cam_pill = Pill(_("Connecting"))
        h.addWidget(self.cam_pill)
        self.truck_pill = Pill(_("No truck"))
        h.addWidget(self.truck_pill)
        self.tamper_pill = Pill("")
        self.tamper_pill.hide()
        h.addWidget(self.tamper_pill)
        h.addStretch(1)
        self.fps = QLabel("")
        self.fps.setObjectName("Muted")
        h.addWidget(self.fps)
        for pill in (self.cam_pill, self.truck_pill, self.tamper_pill):
            pill.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        name.setMinimumWidth(60)
        lay.addLayout(h)
        self.video = VideoView()
        self.video.double_clicked.connect(lambda: page.focus_bay(self))
        self.status_lbl = QLabel(_("IDLE"))
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_lbl = QLabel("0")
        self.count_lbl.setObjectName("BigCount")
        self.exp_lbl = QLabel("/ -")
        self.exp_lbl.setStyleSheet(f"font-size: 26px; color: {theme.c('muted')}; font-weight: 600;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(16)
        self.review_lbl = QLabel("")
        self.review_lbl.setStyleSheet("color: #9A6511; font-weight: 600;")
        self.plate_lbl = QLabel("— — —")
        self.plate_lbl.setObjectName("Plate")
        self.plate_conf = QLabel("")
        self.plate_conf.setObjectName("Muted")
        self.plate_edit = QPushButton()
        self.plate_edit.setIcon(icons.icon("edit"))
        self.plate_edit.setToolTip(_("Correct the plate"))
        self.plate_edit.clicked.connect(self.edit_plate)
        self.gp_lbl = QLabel(_("Gate pass: -"))
        self.gp_lbl.setWordWrap(True)
        self.time_lbl = QLabel(_("Elapsed: 00:00:00"))
        self.time_lbl.setObjectName("Muted")
        self.products_box = QVBoxLayout()
        self.products_box.setSpacing(4)
        self.product_group = QButtonGroup(self)
        self.product_group.idClicked.connect(self._product_chosen)
        self.start_btn = button("Start loading", "Primary", "play", big=True)
        self.start_btn.clicked.connect(self.start_session)
        self.close_btn = button("Close & verify", "Accent", "check", big=True)
        self.close_btn.clicked.connect(self.close_session)
        self.review_btn = button("Review", icon_name="shield")
        self.review_btn.clicked.connect(self.review)
        self.link_btn = button("Gate pass", icon_name="sessions")
        self.link_btn.clicked.connect(self.link_gate_pass)
        self.cancel_btn = button("Cancel", icon_name="x")
        self.cancel_btn.clicked.connect(self.cancel_session)
        cnt = QHBoxLayout()
        cnt.addWidget(self.count_lbl)
        cnt.addWidget(self.exp_lbl, 0, Qt.AlignmentFlag.AlignBottom)
        cnt.addStretch(1)
        pl = QHBoxLayout()
        pl.addWidget(self.plate_lbl)
        pl.addWidget(self.plate_conf)
        pl.addStretch(1)
        pl.addWidget(self.plate_edit)
        small = QHBoxLayout()
        for b in (self.review_btn, self.link_btn, self.cancel_btn):
            small.addWidget(b)
        if not page.compact:
            # one bay: video left, panel right
            body = QHBoxLayout()
            body.setSpacing(14)
            body.addWidget(self.video, 3)
            panel = QVBoxLayout()
            panel.setSpacing(8)
            panel.addWidget(self.status_lbl)
            panel.addLayout(cnt)
            panel.addWidget(self.progress)
            panel.addWidget(self.review_lbl)
            panel.addLayout(pl)
            panel.addWidget(self.gp_lbl)
            panel.addWidget(self.time_lbl)
            panel.addLayout(self.products_box)
            panel.addStretch(1)
            panel.addWidget(self.start_btn)
            panel.addWidget(self.close_btn)
            panel.addLayout(small)
            pw = QWidget()
            pw.setLayout(panel)
            pw.setMinimumWidth(320)
            pw.setMaximumWidth(400)
            body.addWidget(pw, 1)
            lay.addLayout(body, 1)
        else:
            # several bays side by side: video on top, compact two-column panel below
            self.video.setMinimumSize(240, 135)
            lay.addWidget(self.video, 1)
            self.count_lbl.setStyleSheet("font-size: 36px;")
            self.exp_lbl.setStyleSheet(f"font-size: 22px; color: {theme.c('muted')}; font-weight: 600;")
            self.status_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            h.insertWidget(1, self.status_lbl)
            self.fps.hide()  # shown as the camera badge tooltip in side-by-side mode
            info_row = QHBoxLayout()
            info_row.setSpacing(16)
            left = QVBoxLayout()
            left.setSpacing(4)
            left.addLayout(cnt)
            left.addWidget(self.progress)
            left.addWidget(self.review_lbl)
            right = QVBoxLayout()
            right.setSpacing(6)
            right.addLayout(pl)
            right.addWidget(self.gp_lbl)
            right.addWidget(self.time_lbl)
            info_row.addLayout(left, 1)
            info_row.addLayout(right, 1)
            lay.addLayout(info_row)
            lay.addLayout(self.products_box)
            lay.addWidget(self.start_btn)
            lay.addWidget(self.close_btn)
            lay.addLayout(small)
            lay.addStretch(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        rt = self.app.runtimes.get(bay.id)
        self.set_session(rt.session_id if rt else None)

    # ------------------------------------------------------------- state
    @property
    def rt(self):
        return self.app.runtimes.get(self.bay.id)

    def set_session(self, sid):
        self.session_id = sid
        self.refresh()

    def refresh(self):
        sid = self.session_id
        active = bool(sid)
        self.start_btn.setVisible(not active)
        for b in (self.close_btn, self.review_btn, self.link_btn, self.cancel_btn, self.plate_edit):
            b.setVisible(active)
        if not active:
            self.summary = None
            self.status_lbl.setText(_("IDLE") if self.page.compact else _("IDLE - no truck loading"))
            self.status_lbl.setStyleSheet(f"background:{theme.c('surface_alt')}; color:{theme.c('muted')}; "
                                          "border-radius:8px; padding:4px 12px; font-weight:700;")
            self.count_lbl.setText("0")
            self.exp_lbl.setText("/ -")
            self.progress.setValue(0)
            self.plate_lbl.setText("— — —")
            self.plate_conf.setText("")
            self.gp_lbl.setText(_("Gate pass: -"))
            self.review_lbl.setText("")
            self.time_lbl.setText(_("Elapsed: 00:00:00"))
            self._set_products([])
            return
        s = self.app.sessions.summary(sid)
        self.summary = s
        self.status_lbl.setText(_("LOADING") + (f"  ·  {_('auto-started')}" if s.auto_started else ""))
        self.status_lbl.setStyleSheet(f"background:{theme.c('primary')}; color:white; border-radius:8px; "
                                      "padding:4px 12px; font-weight:700;")
        self.count_lbl.setText(str(s.total_counted))
        exp = s.total_expected if s.gate_pass else None
        self.exp_lbl.setText(f"/ {exp}" if exp is not None else "/ -")
        if exp:
            v = int(1000 * min(1.0, s.total_counted / exp))
            self.progress.setValue(v)
            name = "Over" if s.total_counted > exp else ("Done" if s.total_counted == exp else "")
        else:
            self.progress.setValue(0)
            name = ""
        if self.progress.objectName() != name:
            self.progress.setObjectName(name)
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
        self.plate_lbl.setText(s.plate_text or "— — —")
        self.plate_conf.setText(f"{s.plate_confidence:.0%}" if s.plate_confidence else "")
        gp = s.gate_pass
        self.gp_lbl.setText(f"<b>{_('Gate pass')}:</b> {gp.number} · {gp.customer}" + (
            f" · {_('vehicle')} {gp.vehicle_no}" if gp.vehicle_no else "") if gp else
            f"<span style='color:{theme.c('danger')}'>{_('No gate pass linked')}</span>")
        self.review_lbl.setText(f"⚠ {s.total_pending} {_('count(s) need supervisor review')}" if s.total_pending else "")
        self.review_btn.setText(f"{_('Review')} ({s.total_pending})" if s.total_pending else _("Review"))
        self._set_products(s.lines)

    def _set_products(self, lines):
        while self.products_box.count():
            it = self.products_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for b in self.product_group.buttons():
            self.product_group.removeButton(b)
        rt = self.rt
        active = rt.active_product_id if rt else None
        for l in lines:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            rb = QRadioButton(l.name)
            rb.setToolTip(_("Counts of this item type go to the selected product"))
            self.product_group.addButton(rb, l.product_id)
            if l.product_id == active:
                rb.setChecked(True)
            h.addWidget(rb, 1)
            exp = "-" if l.expected is None else str(l.expected)
            col = theme.c("success") if l.ok else (theme.c("danger") if l.expected is not None and l.counted > l.expected
                                                   else theme.c("text"))
            v = QLabel(f"<b style='color:{col}'>{l.counted}</b> / {exp}" + (f"  <span style='color:#9A6511'>+{l.pending}?</span>"
                                                                            if l.pending else ""))
            h.addWidget(v)
            self.products_box.addWidget(w)

    def _product_chosen(self, pid):
        if self.rt:
            self.rt.active_product_id = pid

    def tick(self):
        if self.summary and self.session_id:
            self.time_lbl.setText(f"{_('Elapsed')}: {fmt_elapsed(time.time() - self.summary.started_at)}")

    # ------------------------------------------------------------- live updates
    def on_frame(self, frame, status):
        if frame is None:
            self.video.set_frame(None, status.get("message", ""))
        else:
            self.video.set_frame(frame)
        if status.get("online"):
            self.cam_pill.set_state(_("Camera online"), "ok")
        else:
            self.cam_pill.set_state(_("Camera offline"), "bad")
        if "truck" in status and status["truck"] != getattr(self, "_truck_shown", None):
            self._truck_shown = status["truck"]
            self.on_truck(status["truck"])
        t = status.get("tamper", "ok")
        self.tamper_pill.setVisible(t != "ok")
        if t != "ok":
            self.tamper_pill.set_state(f"⚠ {t}", "bad")
        perf = f"{status.get('fps', 0):.0f} fps · {status.get('infer_ms', 0):.0f} ms"
        self.fps.setText(perf)
        self.cam_pill.setToolTip(perf)

    def on_count(self, ev):
        if ev.get("session_id") and ev["session_id"] == self.session_id:
            self.refresh()

    def on_truck(self, present: bool):
        self.truck_pill.set_state(_("Truck in bay") if present else _("No truck"), "info" if present else "muted")

    # ------------------------------------------------------------- actions
    def start_session(self):
        if not self.rt:
            error(self, _("This bay is not running. Check the camera setup and licence."))
            return
        d = GatePassPicker(self, self.app)
        if not d.exec():
            return
        try:
            self.rt.start_session(self.app.user, d.gate_pass_id)
        except SessionError as e:
            error(self, str(e))

    def close_session(self):
        if not self.session_id or not self.rt:
            return
        s = self.app.sessions.summary(self.session_id)
        if s.gate_pass is None:
            if confirm(self, _("No gate pass is linked to this truck. Link one now?")):
                self.link_gate_pass()
                s = self.app.sessions.summary(self.session_id)
        if not confirm(self, _("Close loading for this truck and compare with the gate pass?")):
            return
        summary = self.rt.close_session(self.app.user)
        if summary:
            self.page.main.sound.play("chime" if summary.status == "cleared" else "beep")
            SessionResultDialog(self, self.app, summary, self.page.main.sound).exec()
            self.page.main.refresh_status()

    def cancel_session(self):
        if not self.session_id:
            return
        sup, reason = ask_supervisor(self, self.app, _("Cancel this loading session? Counts are kept in the audit trail."),
                                     need_reason=True)
        if sup:
            self.rt.cancel_session(sup, reason)

    def review(self):
        if not self.session_id:
            return
        sup, _r = ask_supervisor(self, self.app, _("Review low-confidence counts"))
        if sup:
            ReviewDialog(self, self.app, self.session_id, sup).exec()
            self.refresh()

    def link_gate_pass(self):
        if not self.session_id:
            return
        s = self.app.sessions.summary(self.session_id)
        d = GatePassPicker(self, self.app, s.plate_text or "")
        d.none_btn.hide()
        d.setWindowTitle(_("Link gate pass"))
        if d.exec() and d.gate_pass_id:
            try:
                self.app.sessions.link_gate_pass(self.session_id, d.gate_pass_id, self.app.user)
            except SessionError as e:
                error(self, str(e))
            self.refresh()

    def edit_plate(self):
        if not self.session_id:
            return
        s = self.app.sessions.summary(self.session_id)
        d = PlateDialog(self, s.plate_text, s.plate_image)
        if d.exec():
            self.rt.set_plate_manual(d.text, self.app.user)
            self.refresh()


class LiveBaysPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        self.widgets: dict[int, BayWidget] = {}
        self.focused: BayWidget | None = None
        self.compact = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        self.header = PageHeader("Live Bays")
        self.focus_btn = self.header.add(button("Show all bays"))
        self.focus_btn.clicked.connect(lambda: self.focus_bay(None))
        self.focus_btn.hide()
        lay.addWidget(self.header)
        self.grid_host = QWidget()
        self.grid_host.setObjectName("Page")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        from nomload.ui.widgets import scroll_wrap
        self.scroll = scroll_wrap(self.grid_host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self.scroll, 1)
        self._cols = 0
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("Muted")
        lay.addWidget(self.empty)
        b = main.bridge
        b.frame_ready.connect(self._frame)
        b.counted.connect(self._count)
        b.session.connect(self._session)
        b.plate_read.connect(self._plate)
        b.prompted.connect(self._prompt)

    def rebuild(self):
        for w in self.widgets.values():
            w.timer.stop()
            w.deleteLater()
        self.widgets.clear()
        bays = [b for b in self.app.bays.list(active_only=True) if b.id in self.app.runtimes]
        self.compact = len(bays) > 1
        for b in bays:
            self.widgets[b.id] = BayWidget(self, b)
        self.focused = None
        self._layout()
        lic = self.app.license.status()
        n_cfg = self.app.bays.count()
        if not bays:
            self.empty.setText(_("No bays are running. Add a bay and its camera under Cameras.") if lic.usable
                               else _("Licence expired. Activate NomLoad under Settings → Licence."))
            self.empty.show()
        elif n_cfg > len(bays):
            self.empty.setText(_(f"{n_cfg - len(bays)} bay(s) not started: your licence ({lic.tier_name}) allows "
                                 f"{lic.max_bays} bay(s)."))
            self.empty.show()
        else:
            self.empty.hide()

    def _layout(self):
        while self.grid.count():
            self.grid.takeAt(0)
        ws = [self.focused] if self.focused else list(self.widgets.values())
        for w in self.widgets.values():
            w.setVisible(w in ws)
        cols = self._columns(len(ws))
        self._cols = cols
        for c in range(4):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        for w in ws:
            # equal columns that may shrink below their natural width instead of overflowing
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            w.setMinimumWidth(360)
        rows = (len(ws) + cols - 1) // max(1, cols)
        avail = self.scroll.viewport().height()
        for i, w in enumerate(ws):
            # fill the screen when everything fits; otherwise keep a usable size and scroll
            w.setMinimumHeight(max(430, (avail - 14 * (rows - 1)) // rows) if rows > 1 else min(380, avail))
            self.grid.addWidget(w, i // cols, i % cols)
        self.focus_btn.setVisible(self.focused is not None)

    def _columns(self, n: int) -> int:
        if n <= 1:
            return 1
        w = self.scroll.viewport().width() or self.width()
        if w >= 2400 and n >= 3:
            return 3
        return 2 if w >= 900 else 1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.widgets:
            self._layout()

    def showEvent(self, e):
        super().showEvent(e)
        # the page gets its real width only when shown: lay the bays out again
        if self.widgets:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._layout)

    def focus_bay(self, w):
        self.focused = None if (w is None or self.focused is w) else w
        self._layout()

    # ------------------------------------------------------------- bridge slots
    def _frame(self, bay_id, frame, status):
        w = self.widgets.get(bay_id)
        if w and w.isVisible() and self.isVisible():
            w.on_frame(frame, status)

    def _count(self, bay_id, ev):
        w = self.widgets.get(bay_id)
        if w:
            w.on_count(ev)

    def _session(self, bay_id, sid):
        w = self.widgets.get(bay_id)
        if w:
            w.set_session(sid)

    def _plate(self, bay_id, text, conf, img):
        w = self.widgets.get(bay_id)
        if w:
            w.refresh()

    def _prompt(self, bay_id, kind, data):
        w = self.widgets.get(bay_id)
        if not w:
            return
        if kind == "truck":
            w.on_truck(data.get("present", False))
        elif kind == "auto_started":
            self.main.toast({"severity": "info", "title": _("Truck detected"),
                             "message": f"{w.bay.name}: {_('loading session started automatically. Select the gate pass.')}"})
        elif kind == "gate_pass_match":
            if confirm(self, f"{_('Plate')} {data['plate']} {_('matches gate pass')} {data['number']}. "
                             f"{_('Link it to this loading session?')}"):
                try:
                    self.app.sessions.link_gate_pass(data["session_id"], data["gate_pass_id"], self.app.user)
                except SessionError as e:
                    error(self, str(e))
                w.refresh()
        elif kind == "truck_left":
            if self.app.settings.get("auto_close_on_truck_exit") and w.rt and w.session_id:
                summary = w.rt.close_session(None)
                if summary:
                    self.main.sound.play("chime" if summary.status == "cleared" else "beep")
                    SessionResultDialog(self, self.app, summary, self.main.sound).exec()
                return
            self.main.toast({"severity": "warning", "title": _("Truck left the bay"),
                             "message": f"{w.bay.name}: {_('the truck is no longer visible. Close & verify the loading now.')}"})
            self.main.sound.play("beep")

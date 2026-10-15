"""Settings: company, counting, performance, sessions, alerts, cameras, OCR, licence, data."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from nomload import theme
from nomload.config import data_home
from nomload.core.detector import available_providers
from nomload.i18n import LANGUAGES, _
from nomload.licensing.license import request_code
from nomload.services.alerts import KINDS
from nomload.services.context import audit
from nomload.ui.pages.common import open_folder
from nomload.ui.widgets import Card, PageHeader, button, error, info


class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        s = self.app.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(sc)
        host = QWidget()
        host.setObjectName("Page")
        sc.setWidget(host)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        hdr = PageHeader("Settings")
        save = hdr.add(button("Save settings", "Primary", "check"))
        save.clicked.connect(self.save)
        lay.addWidget(hdr)
        self.w: dict[str, QWidget] = {}
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        def card(title, r, c, span=1):
            cd = Card(title)
            f = QFormLayout()
            f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            cd.lay.addLayout(f)
            grid.addWidget(cd, r, c, 1, span)
            return cd, f

        def line(key, secret=False, ph=""):
            e = QLineEdit(str(s.get(key) or ""))
            if secret:
                e.setEchoMode(QLineEdit.EchoMode.Password)
            e.setPlaceholderText(ph)
            self.w[key] = e
            return e

        def spin(key, lo, hi, suffix=""):
            e = QSpinBox()
            e.setRange(lo, hi)
            e.setValue(int(s.get(key) or 0))
            e.setSuffix(suffix)
            self.w[key] = e
            return e

        def dspin(key, lo, hi, step=0.05, dec=2, suffix=""):
            e = QDoubleSpinBox()
            e.setRange(lo, hi)
            e.setSingleStep(step)
            e.setDecimals(dec)
            e.setValue(float(s.get(key) or 0))
            e.setSuffix(suffix)
            self.w[key] = e
            return e

        def check(key, text):
            e = QCheckBox(_(text))
            e.setChecked(bool(s.get(key)))
            self.w[key] = e
            return e

        # company
        cd, f = card("Company", 0, 0)
        f.addRow(_("Company name"), line("company_name"))
        f.addRow(_("Address / phone"), line("company_address"))
        lh = QHBoxLayout()
        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(120, 60)
        self._show_logo()
        lb = button("Choose logo...")
        lb.clicked.connect(self.choose_logo)
        lh.addWidget(self.logo_lbl)
        lh.addWidget(lb)
        lh.addStretch(1)
        f.addRow(_("Logo on reports"), lh)
        lang = QComboBox()
        for k, v in LANGUAGES.items():
            lang.addItem(v, k)
        lang.setCurrentIndex(max(0, lang.findData(s.get("language"))))
        self.w["language"] = lang
        f.addRow(_("Language"), lang)
        # counting
        cd, f = card("Counting & matching", 0, 1)
        f.addRow(_("Allowed difference (units)"), spin("tolerance_units", 0, 10000))
        f.addRow(_("Allowed difference (%)"), dspin("tolerance_pct", 0, 50, 0.5, 1, " %"))
        f.addRow(_("Review counts below confidence"), dspin("review_threshold", 0, 1, 0.05))
        f.addRow(_("Detector confidence threshold"), dspin("detector_conf", 0.05, 0.95, 0.05))
        # performance
        cd, f = card("Performance", 1, 0)
        f.addRow(_("Skip frames between analyses"), spin("frame_skip", 0, 10))
        f.addRow(_("Max processing width"), spin("max_process_width", 320, 1920, " px"))
        f.addRow(_("Inference threads (0 = auto)"), spin("inference_threads", 0, 32))
        gpu = check("use_gpu", "Use GPU (DirectML / CUDA) when available")
        provs = available_providers()
        gpu_ok = any(p in provs for p in ("DmlExecutionProvider", "CUDAExecutionProvider"))
        f.addRow("", gpu)
        pl = QLabel(_("Available") + ": " + ", ".join(p.replace("ExecutionProvider", "") for p in provs) +
                    ("" if gpu_ok else "  ·  " + _("install onnxruntime-directml for GPU")))
        pl.setObjectName("Muted")
        pl.setWordWrap(True)
        f.addRow("", pl)
        # sessions & evidence
        cd, f = card("Sessions & evidence", 1, 1)
        f.addRow(_("Pre-roll video before session"), spin("preroll_s", 0, 120, " s"))
        f.addRow(_("Evidence clip frame rate"), spin("clip_fps", 2, 25, " fps"))
        f.addRow(_("Auto-start after truck seen for"), spin("truck_present_start_s", 1, 120, " s"))
        f.addRow(_("Truck gone after"), spin("truck_absent_close_s", 5, 600, " s"))
        f.addRow("", check("auto_close_on_truck_exit", "Close && verify automatically when the truck leaves"))
        # cameras
        cd, f = card("Cameras", 2, 0)
        f.addRow(_("Camera offline alert after"), spin("camera_offline_alert_s", 5, 3600, " s"))
        f.addRow("", check("tamper_enabled", "Detect camera tampering (covered, blurred, moved)"))
        f.addRow(_("Tamper must last"), spin("tamper_persist_s", 1, 120, " s"))
        # sound
        cd, f = card("Alerts on this PC", 2, 1)
        f.addRow("", check("sound_alerts", "Play alert sounds"))
        f.addRow(_("Volume"), dspin("alert_volume", 0, 1, 0.1, 1))
        tb = button("Test alarm", icon_name="bell")
        tb.clicked.connect(self.test_sound)
        f.addRow("", tb)
        # remote
        cd, f = card("Remote alerts (sent when internet is available)", 3, 0, 2)
        ev = QGridLayout()
        self.ev_checks = {}
        chosen = set(s.get("remote_events") or [])
        for k, (_sev, title) in KINDS.items():
            if k in ("camera_online", "cleared", "session_released", "low_confidence", "plate_mismatch", "mismatch",
                     "camera_offline", "tamper"):
                c = QCheckBox(_(title))
                c.setChecked(k in chosen)
                n = len(self.ev_checks)
                self.ev_checks[k] = c
                ev.addWidget(c, n // 4, n % 4)
        f.addRow(_("Send for"), ev)
        f.addRow("", check("email_enabled", "Email"))
        eh = QHBoxLayout()
        eh.addWidget(line("smtp_host", ph="smtp.gmail.com"))
        eh.addWidget(spin("smtp_port", 1, 65535))
        eh.addWidget(check("smtp_tls", "TLS"))
        f.addRow(_("SMTP server / port"), eh)
        f.addRow(_("SMTP username"), line("smtp_user"))
        f.addRow(_("SMTP password / app password"), line("smtp_password", True))
        f.addRow(_("From address"), line("email_from"))
        f.addRow(_("Send to (comma separated)"), line("email_to"))
        f.addRow("", check("whatsapp_enabled", "WhatsApp (Meta WhatsApp Business Cloud API)"))
        f.addRow(_("Access token"), line("whatsapp_token", True))
        f.addRow(_("Phone number ID"), line("whatsapp_phone_id"))
        f.addRow(_("Send to numbers"), line("whatsapp_to", ph="923001234567, 923211234567"))
        f.addRow("", check("sms_enabled", "SMS via HTTP gateway"))
        f.addRow(_("Gateway URL template"), line("sms_url_template", True,
                                                 "https://gateway.example.pk/send?key=XXX&to={to}&msg={message}"))
        f.addRow(_("Send to numbers"), line("sms_to"))
        qh = QHBoxLayout()
        self.queue_lbl = QLabel("")
        self.queue_lbl.setObjectName("Muted")
        tq = button("Send test alert")
        tq.clicked.connect(self.test_remote)
        fl = button("Send queued now")
        fl.clicked.connect(self.flush)
        qh.addWidget(self.queue_lbl, 1)
        qh.addWidget(tq)
        qh.addWidget(fl)
        f.addRow("", qh)
        # OCR
        cd, f = card("Number plate OCR", 4, 0)
        o = QLabel(_("The built-in OCR is used by default. To use a PaddleOCR recognition model exported to ONNX, "
                     "choose the model and its dictionary file."))
        o.setWordWrap(True)
        o.setObjectName("Muted")
        f.addRow(o)
        f.addRow(_("PaddleOCR model (.onnx)"), self._file_row("paddle_rec_model", "ONNX (*.onnx)"))
        f.addRow(_("Dictionary (.txt)"), self._file_row("paddle_rec_dict", "Text (*.txt)"))
        # licence
        self.lic_card, f = card("Licence", 4, 1)
        self.lic_status = QLabel()
        self.lic_status.setStyleSheet("font-size: 16px; font-weight: 700;")
        f.addRow(_("Status"), self.lic_status)
        rc = QHBoxLayout()
        self.req = QLineEdit(request_code())
        self.req.setReadOnly(True)
        cp = button("Copy")
        cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.req.text()))
        rc.addWidget(self.req, 1)
        rc.addWidget(cp)
        f.addRow(_("PC request code"), rc)
        self.key = QLineEdit()
        self.key.setPlaceholderText("NLC-XXXXXX-XXXXXX-...")
        ak = button("Activate", "Primary", "key")
        ak.clicked.connect(self.activate)
        kh = QHBoxLayout()
        kh.addWidget(self.key, 1)
        kh.addWidget(ak)
        f.addRow(_("Licence key"), kh)
        rv = button("Import revocation list...")
        rv.clicked.connect(self.import_revocation)
        f.addRow("", rv)
        # data
        cd, f = card("Data", 5, 0, 2)
        dh = QHBoxLayout()
        dl = QLabel(str(data_home()))
        dl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ob = button("Open folder")
        ob.clicked.connect(lambda: open_folder(data_home()))
        bk = button("Backup database...", icon_name="download")
        bk.clicked.connect(self.backup)
        dh.addWidget(dl, 1)
        dh.addWidget(ob)
        dh.addWidget(bk)
        f.addRow(_("Data folder"), dh)
        lay.addStretch(1)

    def _file_row(self, key, flt):
        h = QHBoxLayout()
        e = QLineEdit(self.app.settings.get(key) or "")
        self.w[key] = e
        b = button("...")
        b.setFixedWidth(44)
        b.clicked.connect(lambda: self._pick(e, flt))
        h.addWidget(e, 1)
        h.addWidget(b)
        return h

    def _pick(self, e, flt):
        p, _f = QFileDialog.getOpenFileName(self, "", "", flt)
        if p:
            e.setText(p)

    def showEvent(self, ev):
        super().showEvent(ev)
        st = self.app.license.status()
        col = theme.c("success") if st.licensed else (theme.c("accent") if st.usable else theme.c("danger"))
        extra = f" · {st.max_bays if st.max_bays < 255 else 'unlimited'} bay(s)" if st.usable else ""
        exp = f" · {st.days_left} day(s) left" if st.licensed and st.days_left is not None else ""
        self.lic_status.setText(f"<span style='color:{col}'>{st.label}</span>{extra}{exp} &nbsp; "
                                f"<span style='font-weight:400'>{st.message}</span>")
        self.queue_lbl.setText(f"{self.app.alerts.pending_count()} {_('message(s) waiting in the outbox')}")

    def _show_logo(self):
        p = self.app.settings.get("company_logo")
        if p and Path(p).exists():
            self.logo_lbl.setPixmap(QPixmap(p).scaled(120, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
        else:
            self.logo_lbl.setText(_("(none)"))

    def choose_logo(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Company logo"), "", "Images (*.png *.jpg *.jpeg)")
        if p:
            dst = data_home() / ("company_logo" + Path(p).suffix.lower())
            shutil.copy2(p, dst)
            self.app.settings.set("company_logo", str(dst))
            self._show_logo()

    def save(self):
        s = self.app.settings
        changed = {}
        for k, w in self.w.items():
            if isinstance(w, QLineEdit):
                v = w.text().strip()
            elif isinstance(w, QCheckBox):
                v = w.isChecked()
            elif isinstance(w, QComboBox):
                v = w.currentData()
            elif isinstance(w, QDoubleSpinBox):
                v = float(w.value())
            else:
                v = int(w.value())
            if s.get(k) != v:
                changed[k] = "***" if "password" in k or "token" in k or "template" in k else v
                s.set(k, v)
        ev = [k for k, c in self.ev_checks.items() if c.isChecked()]
        if set(ev) != set(s.get("remote_events") or []):
            s.set("remote_events", ev)
            changed["remote_events"] = ev
        audit(self.app.db, self.app.user, "settings_changed", "settings", "", changed)
        restart_keys = {"frame_skip", "max_process_width", "use_gpu", "inference_threads", "detector_conf",
                        "review_threshold", "preroll_s", "clip_fps", "tamper_enabled", "tamper_persist_s",
                        "paddle_rec_model", "paddle_rec_dict"}
        if restart_keys & set(changed):
            self.main.reload_models_and_bays()
        if "language" in changed:
            info(self, _("Restart NomLoad to apply the language."))
        info(self, _("Settings saved."))

    def test_sound(self):
        self.main.sound.start_alarm()
        info(self, _("Alarm playing. Press OK to stop."))
        self.main.sound.stop_alarm()

    def test_remote(self):
        self.save()
        self.app.alerts.queue_remote("NomLoad test alert", f"Test message from {self.app.settings.get('company_name')}.")
        self.flush()

    def flush(self):
        n = self.app.alerts.flush()
        last = self.app.db.one("SELECT last_error FROM remote_queue WHERE status='queued' AND last_error IS NOT NULL "
                               "ORDER BY id DESC LIMIT 1")
        msg = f"{n} {_('message(s) sent.')}"
        if last:
            msg += f"\n{_('Last error')}: {last['last_error']}"
        if not self.app.alerts.online():
            msg = _("No internet connection. Messages stay in the outbox and are sent automatically later.")
        info(self, msg)
        self.queue_lbl.setText(f"{self.app.alerts.pending_count()} {_('message(s) waiting in the outbox')}")

    def activate(self):
        try:
            st = self.app.license.activate(self.key.text())
        except Exception as e:
            error(self, str(e))
            return
        audit(self.app.db, self.app.user, "licence_activated", "licence", st.key_id, st.label)
        info(self, f"{_('Licence activated')}: {st.label}")
        self.showEvent(None)
        self.main.refresh_status()
        self.main.restart_bays()

    def import_revocation(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Revocation list"), "", "NomLoad revocation (*.nlr)")
        if p:
            try:
                n = self.app.license.import_revocation(p)
            except Exception as e:
                error(self, f"{_('Invalid revocation file')}: {e}")
                return
            info(self, f"{n} {_('revoked key(s) loaded.')}")
            self.showEvent(None)

    def backup(self):
        p, _f = QFileDialog.getSaveFileName(self, _("Backup database"),
                                            str(Path.home() / f"nomload_backup_{time.strftime('%Y%m%d_%H%M')}.db"),
                                            "SQLite (*.db)")
        if p:
            import sqlite3
            dst = sqlite3.connect(p)
            self.app.db.conn().backup(dst)
            dst.close()
            audit(self.app.db, self.app.user, "database_backup", "data", p)
            info(self, _("Backup saved."))

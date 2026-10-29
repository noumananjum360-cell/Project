"""Camera & device settings: USB / RTSP source, diagnostics, live preview (memory only) and the recognition-provider
settings. Recognition stays OFF unless a real, validated provider is installed."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from app.integrations.camera_opencv import OpenCVCamera, discover_usb, mask_url, test_camera
from app.integrations.recognition import get_provider
from app.ui.reusable_widgets import PageHeader, button, card, guarded, info, muted, run_task, subtitle
from app.ui.theme import CRIT, OK, palette


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img: QImage | None = None
        self.text = "Camera is off"

    def set_frame(self, fr):
        if fr is None:
            self.img = None
        else:
            import cv2
            rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            self.img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(palette()["view"]))
        if self.img is None:
            p.setPen(QColor("#93A3B5")); p.drawText(self.rect(), Qt.AlignCenter, self.text)
            return
        s = min(self.width() / self.img.width(), self.height() / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), self.img)


class CameraPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.cam: OpenCVCamera | None = None
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        lay.addWidget(PageHeader("Camera", "Optional - NomLoyal works fully without a camera"))
        row = QHBoxLayout(); row.setSpacing(10)
        left = QVBoxLayout()
        f = QFormLayout(); f.setSpacing(8)
        s = ctx.settings
        self.kind = QComboBox(); self.kind.addItem("USB webcam", "usb"); self.kind.addItem("IP camera (RTSP)", "rtsp")
        self.kind.setCurrentIndex(max(0, self.kind.findData(s.get("camera_kind"))))
        self.source = QLineEdit(s.get("camera_source") or "")
        self.source.setPlaceholderText("USB: 0, 1, 2…   RTSP: rtsp://user:password@192.168.1.64:554/Streaming/Channels/102")
        self.source.setEchoMode(QLineEdit.Password if (s.get("camera_kind") == "rtsp") else QLineEdit.Normal)
        self.kind.currentIndexChanged.connect(lambda _i: self.source.setEchoMode(
            QLineEdit.Password if self.kind.currentData() == "rtsp" else QLineEdit.Normal))
        self.fps = QSpinBox(); self.fps.setRange(1, 30); self.fps.setValue(int(s.get("camera_fps") or 10)); self.fps.setSuffix(" fps")
        self.width_ = QSpinBox(); self.width_.setRange(320, 1920); self.width_.setSingleStep(160)
        self.width_.setValue(int(s.get("camera_width") or 960)); self.width_.setSuffix(" px")
        f.addRow("Camera type", self.kind); f.addRow("Index / RTSP address", self.source)
        f.addRow("Processing rate", self.fps); f.addRow("Processing width", self.width_)
        cam_card = card(subtitle("Camera connection"))
        cam_card.layout().addLayout(f)
        brow = QHBoxLayout()
        self.b_find = button("Find USB cameras", icon_name="search"); self.b_find.clicked.connect(self._discover)
        self.b_test = button("Test connection", icon_name="check"); self.b_test.clicked.connect(self._test)
        self.b_save = button("Save", "primary", "check"); self.b_save.clicked.connect(self._save)
        for b in (self.b_find, self.b_test, self.b_save):
            brow.addWidget(b)
        brow.addStretch(1)
        cam_card.layout().addLayout(brow)
        self.diag = muted(); cam_card.layout().addWidget(self.diag)
        left.addWidget(cam_card)
        # recognition provider
        rec = card(subtitle("Customer recognition (optional, biometric)"))
        prov = get_provider(s.get("recognition_provider"))
        available, msg = prov.available()
        rf = QFormLayout()
        self.provider = QComboBox(); self.provider.addItem("None installed", "none"); self.provider.setEnabled(False)
        self.rec_enabled = QCheckBox("Enable recognition for consenting, enrolled customers")
        self.rec_enabled.setChecked(bool(s.get("recognition_enabled")) and available)
        self.rec_enabled.setEnabled(available)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0.5, 0.99); self.threshold.setSingleStep(0.01)
        self.threshold.setValue(float(s.get("recognition_threshold") or 0.8)); self.threshold.setEnabled(available)
        self.confirm_cb = QCheckBox("A staff member must confirm every match"); self.confirm_cb.setChecked(True)
        self.confirm_cb.setEnabled(available)
        rf.addRow("Provider", self.provider); rf.addRow("", self.rec_enabled); rf.addRow("Confidence threshold", self.threshold)
        rf.addRow("", self.confirm_cb)
        rec.layout().addLayout(rf)
        status = QLabel(f"<b style='color:{OK if available else CRIT}'>{'Available' if available else 'Not available'}"
                        f"</b> - {msg}")
        status.setWordWrap(True); status.setTextFormat(Qt.RichText)
        rec.layout().addWidget(status)
        rec.layout().addWidget(muted(
            "Recognition is off by default. When a validated provider is installed it may only match customers who gave "
            "biometric consent and enrolled; unknown people are never identified and face images are not stored. Below "
            "the threshold, or when unsure, staff use the loyalty ID / QR / phone lookup instead. Camera angle, "
            "lighting, resolution and face coverings affect reliability - test on site before relying on it."))
        left.addWidget(rec)
        left.addStretch(1)
        row.addLayout(left, 2)
        right = QVBoxLayout()
        self.active = QLabel(); self.active.setAlignment(Qt.AlignCenter)
        self.preview = Preview()
        prow = QHBoxLayout()
        self.b_start = button("Start preview", "primary", "play"); self.b_start.clicked.connect(self.start)
        self.b_stop = button("Stop", icon_name="stop"); self.b_stop.clicked.connect(self.stop)
        self.status = muted()
        prow.addWidget(self.b_start); prow.addWidget(self.b_stop); prow.addStretch(1); prow.addWidget(self.status)
        right.addWidget(self.active); right.addWidget(self.preview, 1); right.addLayout(prow)
        right.addWidget(muted("The preview is shown on this screen only. No video or images are recorded or saved."))
        row.addLayout(right, 3)
        lay.addLayout(row, 1)
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self._indicator(False)

    def refresh(self):
        can = self.ctx.can("camera.manage")
        for w in (self.kind, self.source, self.fps, self.width_, self.b_save, self.b_find):
            w.setEnabled(can)

    def _indicator(self, on: bool):
        self.active.setText("●  CAMERA ACTIVE" if on else "Camera off")
        self.active.setStyleSheet(f"background:{CRIT}; color:white; font-weight:700; padding:6px; border-radius:8px;"
                                  if on else f"color:{palette()['muted']}; padding:6px;")
        self.b_start.setEnabled(not on); self.b_stop.setEnabled(on)

    def _save(self):
        s = self.ctx.settings
        if not self.ctx.can("camera.manage"):
            info(self, "Camera", "Only an Admin can change camera settings."); return
        s.set("camera_kind", self.kind.currentData()); s.set("camera_source", self.source.text().strip())
        s.set("camera_fps", self.fps.value()); s.set("camera_width", self.width_.value())
        s.set("recognition_enabled", self.rec_enabled.isChecked() and self.rec_enabled.isEnabled())
        s.set("recognition_threshold", self.threshold.value())
        from app.security.audit import audit
        audit(self.ctx.db, self.ctx.user, "camera_settings_saved", "camera", "",
              {"kind": self.kind.currentData(), "source": mask_url(self.source.text().strip())})
        info(self, "Camera", "Saved.")

    def _discover(self):
        def done(found):
            self.diag.setText(f"USB cameras found at index: {', '.join(map(str, found))}" if found
                              else "No USB camera found.")
            if found and self.kind.currentData() == "usb":
                self.source.setText(str(found[0]))
        run_task(self, "Looking for USB cameras…", discover_usb, done)

    def _test(self):
        kind, src = self.kind.currentData(), self.source.text().strip() or "0"

        def done(res):
            ok, msg, frame = res
            self.diag.setText(("✔ " if ok else "✖ ") + msg + ("" if kind == "usb" else f"  ({mask_url(src)})"))
            if ok:
                self.preview.set_frame(frame)
        run_task(self, "Connecting to the camera…", lambda: test_camera(kind, src), done)

    def start(self):
        if not self.ctx.can("camera.view"):
            return
        self.stop()
        self.cam = OpenCVCamera(self.kind.currentData(), self.source.text().strip() or "0", self.fps.value(),
                                self.width_.value())
        self.cam.start()
        self._indicator(True)
        self.timer.start(int(1000 / max(1, self.fps.value())))
        from app.security.audit import audit
        audit(self.ctx.db, self.ctx.user, "camera_preview_started", "camera", "")

    def stop(self):
        if self.cam:
            self.cam.stop(); self.cam = None
            from app.security.audit import audit
            audit(self.ctx.db, self.ctx.user, "camera_preview_stopped", "camera", "")
        self.timer.stop()
        self.preview.set_frame(None)
        self._indicator(False)
        self.status.setText("")

    def _tick(self):
        if not self.cam:
            return
        st = self.cam.status()
        self.status.setText(f"{st.message}" + (f" · {st.fps:.0f} fps" if st.fps else ""))
        fr = self.cam.latest()
        if fr is not None:
            self.preview.set_frame(fr)

    def hideEvent(self, ev):
        self.stop()                       # never keep a camera running in the background
        super().hideEvent(ev)

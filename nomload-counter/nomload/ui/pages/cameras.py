"""Cameras: bays, camera sources (RTSP helper, test connection) and calibration."""
from __future__ import annotations

import copy
import math

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from nomload import theme
from nomload.core.geometry import CountGeometry
from nomload.core.video import BRANDS, SourceSpec, list_usb_cameras, mask_url, rtsp_url, test_connection
from nomload.i18n import _
from nomload.ui.dialogs import Base
from nomload.ui.widgets import (Card, PageHeader, bgr_to_qimage, button, confirm, error, fill_table, info, make_table,
                                selected_data)


# ======================================================================= calibration canvas
class CalibCanvas(QWidget):
    changed = Signal()

    def __init__(self, frame: np.ndarray, geo: CountGeometry):
        super().__init__()
        self.frame = frame
        self.img = bgr_to_qimage(frame)
        self.geo = geo
        self.tool = "line"
        self.temp: list[tuple[float, float]] = []
        self.drag_start = None
        self.setMinimumSize(720, 405)
        self.setMouseTracking(True)
        self.mouse = None
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _rect(self) -> QRectF:
        w, h = self.width(), self.height()
        iw, ih = self.img.width(), self.img.height()
        s = min(w / iw, h / ih)
        return QRectF((w - iw * s) / 2, (h - ih * s) / 2, iw * s, ih * s)

    def to_norm(self, p: QPointF):
        r = self._rect()
        return (min(1, max(0, (p.x() - r.x()) / r.width())), min(1, max(0, (p.y() - r.y()) / r.height())))

    def to_px(self, n) -> QPointF:
        r = self._rect()
        return QPointF(r.x() + n[0] * r.width(), r.y() + n[1] * r.height())

    def set_tool(self, t: str):
        self.tool = t
        self.temp = []
        self.update()

    def mousePressEvent(self, e):
        n = self.to_norm(e.position())
        if e.button() == Qt.MouseButton.RightButton:
            self._finish_poly()
            return
        if self.tool in ("line", "plate"):
            self.drag_start = n
        else:
            self.temp.append(n)
        self.update()

    def mouseMoveEvent(self, e):
        self.mouse = self.to_norm(e.position())
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag_start is None:
            return
        n = self.to_norm(e.position())
        a = self.drag_start
        self.drag_start = None
        if math.hypot(n[0] - a[0], n[1] - a[1]) < 0.02:
            return
        if self.tool == "line":
            self.geo.mode = "line"
            self.geo.p1, self.geo.p2 = a, n
        elif self.tool == "plate":
            self.geo.plate_roi = (min(a[0], n[0]), min(a[1], n[1]), max(a[0], n[0]), max(a[1], n[1]))
        self.changed.emit()
        self.update()

    def mouseDoubleClickEvent(self, e):
        self._finish_poly()

    def _finish_poly(self):
        if len(self.temp) >= 3:
            if self.tool == "zone":
                self.geo.mode = "zone"
                self.geo.zone = list(self.temp)
            elif self.tool == "ignore":
                self.geo.ignore_zones.append(list(self.temp))
            self.changed.emit()
        self.temp = []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.c("video_bg")))
        r = self._rect()
        p.drawImage(r, self.img)
        g = self.geo
        amber = QColor("#E8A33D")
        # ignore zones
        for z in g.ignore_zones:
            p.setPen(QPen(QColor(200, 200, 200), 2, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(120, 120, 120, 110), Qt.BrushStyle.BDiagPattern))
            p.drawPolygon(QPolygonF([self.to_px(q) for q in z]))
        if g.plate_roi:
            x0, y0, x1, y1 = g.plate_roi
            p.setPen(QPen(QColor(60, 200, 60), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self.to_px((x0, y0)), self.to_px((x1, y1))))
            p.drawText(self.to_px((x0, y0)) + QPointF(4, -4), _("Plate region"))
        if g.mode == "zone" and len(g.zone) >= 3:
            p.setPen(QPen(amber, 3))
            p.setBrush(QColor(232, 163, 61, 60))
            p.drawPolygon(QPolygonF([self.to_px(q) for q in g.zone]))
        else:
            a, b = self.to_px(g.p1), self.to_px(g.p2)
            band = g.band * r.width()
            dx, dy = b.x() - a.x(), b.y() - a.y()
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L
            # orientation so that the arrow points to the inside (truck) side
            pg = g.to_pixels(1000, 1000)
            mid_n = ((g.p1[0] + g.p2[0]) / 2, (g.p1[1] + g.p2[1]) / 2)
            if pg.signed_distance((mid_n[0] * 1000 + nx * 10, mid_n[1] * 1000 + ny * 10)) < 0:
                nx, ny = -nx, -ny
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(232, 163, 61, 55))
            p.drawPolygon(QPolygonF([QPointF(a.x() - nx * band, a.y() - ny * band), QPointF(b.x() - nx * band, b.y() - ny * band),
                                     QPointF(b.x() + nx * band, b.y() + ny * band), QPointF(a.x() + nx * band, a.y() + ny * band)]))
            p.setPen(QPen(amber, 4))
            p.drawLine(a, b)
            m = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            tip = QPointF(m.x() + nx * 60, m.y() + ny * 60)
            p.drawLine(m, tip)
            for ang in (2.6, -2.6):
                ca, sa = math.cos(ang), math.sin(ang)
                vx, vy = nx * ca - ny * sa, nx * sa + ny * ca
                p.drawLine(tip, QPointF(tip.x() + vx * 16, tip.y() + vy * 16))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(tip + QPointF(6, 4), _("INTO TRUCK (+1)"))
        if self.temp:
            p.setPen(QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine))
            pts = [self.to_px(q) for q in self.temp] + ([self.to_px(self.mouse)] if self.mouse else [])
            p.drawPolyline(QPolygonF(pts))
        if self.drag_start and self.mouse:
            p.setPen(QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine))
            if self.tool == "line":
                p.drawLine(self.to_px(self.drag_start), self.to_px(self.mouse))
            else:
                p.drawRect(QRectF(self.to_px(self.drag_start), self.to_px(self.mouse)))


class CalibrationDialog(QDialog):
    def __init__(self, parent, app, cam):
        super().__init__(parent)
        self.app = app
        self.cam = cam
        self.setWindowTitle(f"{_('Calibrate')} - {cam.name}")
        self.resize(1200, 820)
        lay = QVBoxLayout(self)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok, frame, msg = test_connection(cam.source, 8)
        QApplication.restoreOverrideCursor()
        if not ok:
            frame = cam.reference if cam.reference is not None else np.full((360, 640, 3), 40, np.uint8)
            lay.addWidget(QLabel(f"⚠ {_('Could not grab a live frame')}: {msg}"))
        self.frame = frame
        self.geo = copy.deepcopy(cam.geometry)
        tools = QHBoxLayout()
        self.group = QButtonGroup(self)
        defs = [("line", _("Counting line (drag)")), ("zone", _("Counting zone (click points)")),
                ("ignore", _("Ignore zone (click points)")), ("plate", _("Plate region (drag)"))]
        for i, (k, label) in enumerate(defs):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.group.addButton(b, i)
            tools.addWidget(b)
        self.group.idClicked.connect(lambda i: self.canvas.set_tool(defs[i][0]))
        flip = button("Flip direction", icon_name="refresh")
        flip.clicked.connect(self.flip)
        clr = button("Clear ignore zones")
        clr.clicked.connect(self.clear_ignore)
        tools.addWidget(flip)
        tools.addWidget(clr)
        lay.addLayout(tools)
        hint = QLabel(_("Draw the counting line across the truck entrance. The arrow must point INTO the truck. "
                        "For polygons click the corners and double-click (or right-click) to finish. "
                        "Ignore zones hide areas such as the stock pile or a walkway."))
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        self.canvas = CalibCanvas(frame, self.geo)
        lay.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(_("Line tolerance band")))
        self.band = QSlider(Qt.Orientation.Horizontal)
        self.band.setRange(5, 60)
        self.band.setValue(int(self.geo.band * 1000))
        self.band.valueChanged.connect(self._band)
        row.addWidget(self.band, 1)
        self.ref = QCheckBox(_("Save this view as the tamper-detection reference"))
        self.ref.setChecked(ok)
        row.addWidget(self.ref)
        if self.cam.role == "count":
            mode_l = QLabel()
            mode_l.setObjectName("Muted")
        lay.addLayout(row)
        bb = QHBoxLayout()
        bb.addStretch(1)
        c = button("Cancel")
        c.clicked.connect(self.reject)
        s = button("Save calibration", "Primary", "check")
        s.clicked.connect(self.save)
        bb.addWidget(c)
        bb.addWidget(s)
        lay.addLayout(bb)

    def _band(self, v):
        self.geo.band = v / 1000.0
        self.canvas.update()

    def flip(self):
        self.geo.in_side *= -1
        self.canvas.update()

    def clear_ignore(self):
        self.geo.ignore_zones = []
        self.canvas.update()

    def save(self):
        ref = self.frame if self.ref.isChecked() else None
        self.app.bays.save_calibration(self.app.user, self.cam.id, self.geo, ref)
        rt = self.app.runtimes.get(self.cam.bay_id)
        if rt and rt.cam and rt.cam.id == self.cam.id:
            rt.update_geometry(self.geo, ref)
        self.accept()


# ======================================================================= camera dialog
class CameraDialog(Base):
    def __init__(self, parent, app, bay_id: int, cam=None):
        super().__init__(parent, "Edit camera" if cam else "Add camera", 640)
        self.app = app
        self.bay_id = bay_id
        self.cam = cam
        f = QFormLayout()
        self.name = QLineEdit(cam.name if cam else "Counting camera")
        self.role = QComboBox()
        self.role.addItem(_("Counting camera (truck entrance)"), "count")
        self.role.addItem(_("Number plate camera"), "plate")
        if cam:
            self.role.setCurrentIndex(self.role.findData(cam.role))
        self.kind = QComboBox()
        for k, v in (("rtsp", _("IP camera / NVR (RTSP)")), ("usb", _("USB webcam")), ("file", _("Video file (testing)"))):
            self.kind.addItem(v, k)
        f.addRow(_("Name"), self.name)
        f.addRow(_("Role"), self.role)
        f.addRow(_("Source"), self.kind)
        self.lay.addLayout(f)
        self.stack = QStackedWidget()
        # rtsp page
        rp = QWidget()
        rf = QFormLayout(rp)
        self.brand = QComboBox()
        self.brand.addItems(list(BRANDS))
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("192.168.1.64")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(554)
        self.user = QLineEdit("admin")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.channel = QSpinBox()
        self.channel.setRange(1, 64)
        self.sub = QCheckBox(_("Use sub-stream (lower resolution, recommended for slow PCs)"))
        self.url = QLineEdit()
        self.url.setPlaceholderText("rtsp://user:pass@ip:554/...")
        for w in (self.brand,):
            w.currentIndexChanged.connect(self._build_url)
        for w in (self.ip, self.user, self.pw):
            w.textChanged.connect(self._build_url)
        for w in (self.port, self.channel):
            w.valueChanged.connect(self._build_url)
        self.sub.toggled.connect(self._build_url)
        rf.addRow(_("Brand"), self.brand)
        rf.addRow(_("IP address"), self.ip)
        rf.addRow(_("Port"), self.port)
        rf.addRow(_("Username"), self.user)
        rf.addRow(_("Password"), self.pw)
        rf.addRow(_("Channel"), self.channel)
        rf.addRow("", self.sub)
        rf.addRow(_("RTSP URL"), self.url)
        self.stack.addWidget(rp)
        # usb page
        up = QWidget()
        uf = QFormLayout(up)
        self.usb = QComboBox()
        self.usb.setEditable(True)
        scan = button("Scan")
        scan.clicked.connect(self._scan)
        h = QHBoxLayout()
        h.addWidget(self.usb, 1)
        h.addWidget(scan)
        uf.addRow(_("Device index"), h)
        self.usb.addItems(["0", "1", "2"])
        self.stack.addWidget(up)
        # file page
        fp = QWidget()
        ff = QFormLayout(fp)
        self.file = QLineEdit()
        br = button("Browse...")
        br.clicked.connect(self._browse)
        h2 = QHBoxLayout()
        h2.addWidget(self.file, 1)
        h2.addWidget(br)
        self.loop = QCheckBox(_("Loop the video"))
        self.loop.setChecked(True)
        ff.addRow(_("Video file"), h2)
        ff.addRow("", self.loop)
        self.stack.addWidget(fp)
        self.lay.addWidget(self.stack)
        self.kind.currentIndexChanged.connect(self.stack.setCurrentIndex)
        # test
        th = QHBoxLayout()
        tb = button("Test connection", icon_name="live")
        tb.clicked.connect(self.test)
        th.addWidget(tb)
        self.test_msg = QLabel("")
        self.test_msg.setWordWrap(True)
        th.addWidget(self.test_msg, 1)
        self.lay.addLayout(th)
        self.preview = QLabel()
        self.preview.setFixedHeight(220)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"background:{theme.c('video_bg')}; border-radius:8px;")
        self.lay.addWidget(self.preview)
        if cam:
            s = cam.source
            self.kind.setCurrentIndex(self.kind.findData(s.kind))
            if s.kind == "rtsp":
                self.url.setText(s.uri)
            elif s.kind == "usb":
                self.usb.setCurrentText(s.uri)
            else:
                self.file.setText(s.uri)
                self.loop.setChecked(s.loop)
        self.buttons("Save")

    def _build_url(self):
        if self.ip.text().strip():
            self.url.setText(rtsp_url(self.brand.currentText(), self.ip.text(), self.user.text(), self.pw.text(),
                                      self.port.value(), self.channel.value(), self.sub.isChecked()))

    def _scan(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        found = list_usb_cameras()
        QApplication.restoreOverrideCursor()
        self.usb.clear()
        self.usb.addItems([str(i) for i in found] or ["0"])
        self.test_msg.setText(f"{len(found)} {_('USB camera(s) found')}")

    def _browse(self):
        p, _f = QFileDialog.getOpenFileName(self, _("Choose video"), "", "Video (*.mp4 *.avi *.mkv *.mov)")
        if p:
            self.file.setText(p)

    def spec(self) -> SourceSpec:
        k = self.kind.currentData()
        if k == "rtsp":
            return SourceSpec("rtsp", self.url.text().strip())
        if k == "usb":
            return SourceSpec("usb", self.usb.currentText().strip() or "0")
        return SourceSpec("file", self.file.text().strip(), self.loop.isChecked())

    def test(self):
        self.test_msg.setText(_("Connecting..."))
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok, frame, msg = test_connection(self.spec(), 8)
        QApplication.restoreOverrideCursor()
        self.test_msg.setText(("✔ " if ok else "✖ ") + msg)
        self.test_msg.setStyleSheet(f"color:{theme.c('success') if ok else theme.c('danger')}; font-weight:600;")
        if ok:
            self.preview.setPixmap(QPixmap.fromImage(bgr_to_qimage(frame)).scaledToHeight(
                220, Qt.TransformationMode.SmoothTransformation))

    def _accept(self):
        sp = self.spec()
        if not sp.uri and sp.kind != "usb":
            error(self, _("Please enter the camera address or choose a file."))
            return
        geo = self.cam.geometry if self.cam else None
        self.app.bays.save_camera(self.app.user, self.bay_id, self.name.text().strip() or "Camera",
                                  self.role.currentData(), sp, geo, self.cam.id if self.cam else None)
        self.accept()


# ======================================================================= page
class CamerasPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        hdr = PageHeader("Cameras")
        apply = hdr.add(button("Apply & restart bays", "Primary", "refresh"))
        apply.clicked.connect(self.restart)
        lay.addWidget(hdr)
        body = QHBoxLayout()
        body.setSpacing(14)
        bc = Card("Loading bays")
        self.bays = make_table(["Bay", "Auto start", "Active"], 0)
        self.bays.itemSelectionChanged.connect(self.load_cams)
        bc.lay.addWidget(self.bays)
        bb = QHBoxLayout()
        for t, fn, k in (("Add bay", self.add_bay, "plus"), ("Edit", self.edit_bay, "edit")):
            b = button(t, icon_name=k)
            b.clicked.connect(fn)
            bb.addWidget(b)
        bc.lay.addLayout(bb)
        body.addWidget(bc, 2)
        cc = Card("Cameras of the selected bay")
        self.cams = make_table(["Camera", "Role", "Source", "Calibrated", "Active"], 2)
        self.cams.doubleClicked.connect(self.edit_cam)
        cc.lay.addWidget(self.cams)
        cb = QHBoxLayout()
        for t, fn, k, kind in (("Add camera", self.add_cam, "plus", ""), ("Edit", self.edit_cam, "edit", ""),
                               ("Calibrate", self.calibrate, "cameras", "Accent"), ("Disable", self.disable_cam, "x", "")):
            b = button(t, kind, k)
            b.clicked.connect(fn)
            cb.addWidget(b)
        cc.lay.addLayout(cb)
        self.lic = QLabel("")
        self.lic.setObjectName("Muted")
        cc.lay.addWidget(self.lic)
        body.addWidget(cc, 5)
        lay.addLayout(body, 1)
        help_c = Card("RTSP tips")
        t = QLabel(_("Hikvision: rtsp://user:pass@IP:554/Streaming/Channels/101 (102 = sub-stream). "
                     "Dahua / CP Plus: rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0. "
                     "Use the sub-stream on slower PCs. The PC and the camera/NVR must be on the same network. "
                     "Place the counting camera high, looking down at the truck entrance."))
        t.setWordWrap(True)
        t.setObjectName("Muted")
        help_c.lay.addWidget(t)
        lay.addWidget(help_c)

    def showEvent(self, e):
        super().showEvent(e)
        self.load_bays()

    def load_bays(self):
        bays = self.app.bays.list()
        self._bays = bays
        fill_table(self.bays, [[b.name, "✔" if b.auto_session else "", "✔" if b.active else ""] for b in bays],
                   [b.id for b in bays])
        if bays:
            self.bays.selectRow(0)
        st = self.app.license.status()
        self.lic.setText(f"{_('Licence')}: {st.label} · {_('bays allowed')}: "
                         f"{'unlimited' if st.max_bays >= 255 else st.max_bays}")
        self.load_cams()

    def _bay(self):
        bid = selected_data(self.bays)
        return next((b for b in self._bays if b.id == bid), None)

    def load_cams(self):
        b = self._bay()
        cams = b.cameras if b else []
        self._cams = cams
        fill_table(self.cams, [[c.name, _("Counting") if c.role == "count" else _("Plate"),
                                f"{c.source.kind.upper()}: {mask_url(c.source.uri)}",
                                "✔" if c.reference is not None else "-", "✔" if c.active else ""] for c in cams],
                   [c.id for c in cams])

    def _cam(self):
        cid = selected_data(self.cams)
        return next((c for c in self._cams if c.id == cid), None)

    def add_bay(self):
        d = Base(self, "Add bay", 420)
        f = QFormLayout()
        name = QLineEdit(f"Bay {len(self._bays) + 1}")
        auto = QCheckBox(_("Start a session automatically when a truck is detected"))
        f.addRow(_("Name"), name)
        f.addRow("", auto)
        d.lay.addLayout(f)
        d.buttons("Save")
        if d.exec():
            try:
                self.app.bays.save_bay(self.app.user, name.text().strip(), auto.isChecked())
            except Exception as e:
                error(self, str(e))
            self.load_bays()

    def edit_bay(self):
        b = self._bay()
        if not b:
            return
        d = Base(self, "Edit bay", 420)
        f = QFormLayout()
        name = QLineEdit(b.name)
        auto = QCheckBox(_("Start a session automatically when a truck is detected"))
        auto.setChecked(b.auto_session)
        act = QCheckBox(_("Active"))
        act.setChecked(b.active)
        f.addRow(_("Name"), name)
        f.addRow("", auto)
        f.addRow("", act)
        d.lay.addLayout(f)
        d.buttons("Save")
        if d.exec():
            self.app.bays.save_bay(self.app.user, name.text().strip(), auto.isChecked(), b.id, act.isChecked())
            self.load_bays()

    def add_cam(self):
        b = self._bay()
        if not b:
            error(self, _("Add a bay first."))
            return
        if CameraDialog(self, self.app, b.id).exec():
            self.load_bays()

    def edit_cam(self):
        c, b = self._cam(), self._bay()
        if c and b and CameraDialog(self, self.app, b.id, c).exec():
            self.load_bays()

    def calibrate(self):
        c = self._cam()
        if c and CalibrationDialog(self, self.app, c).exec():
            self.load_bays()

    def disable_cam(self):
        c = self._cam()
        if c and confirm(self, f"{_('Disable camera')} {c.name}?"):
            self.app.bays.delete_camera(self.app.user, c.id)
            self.load_bays()

    def restart(self):
        self.main.restart_bays()
        info(self, _("Bays restarted with the new camera settings."))

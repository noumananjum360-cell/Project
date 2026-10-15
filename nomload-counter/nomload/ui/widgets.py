"""Reusable widgets: cards, KPI tiles, bar charts, video view, toasts."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from nomload import theme
from nomload.i18n import _
from nomload.ui import icons


def bgr_to_qimage(frame: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def button(text: str, kind: str = "", icon_name: str | None = None, big: bool = False) -> QPushButton:
    b = QPushButton(_(text).replace("&", "&&"))
    if kind:
        b.setObjectName(kind)
    if icon_name:
        col = "#FFFFFF" if kind in ("Primary", "Success", "Danger") else ("#1B2A4E" if kind == "Accent" else None)
        b.setIcon(icons.icon(icon_name, col))
        b.setIconSize(QSize(18, 18))
    if big:
        b.setProperty("big", True)
        b.setMinimumHeight(48)
        f = b.font()
        f.setPixelSize(16)
        b.setFont(f)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)
        if title:
            self.title = QLabel(_(title))
            self.title.setObjectName("CardTitle")
            self.lay.addWidget(self.title)


class KpiCard(QFrame):
    def __init__(self, label: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        self.value = QLabel(value)
        self.value.setObjectName("KpiValue")
        self.label = QLabel(_(label))
        self.label.setObjectName("KpiLabel")
        lay.addWidget(self.value)
        lay.addWidget(self.label)
        self.setMinimumHeight(92)

    def set(self, value, color: str | None = None):
        self.value.setText(str(value))
        self.value.setStyleSheet(f"color: {color};" if color else "")


class PageHeader(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 6)
        self.title = QLabel(_(title))
        self.title.setObjectName("PageTitle")
        self.lay.addWidget(self.title)
        self.lay.addStretch(1)

    def add(self, w: QWidget):
        self.lay.addWidget(w)
        return w


class Pill(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.set_state(text, "muted")

    def set_state(self, text: str, state: str):
        colors = {"ok": (theme.c("success_soft"), theme.c("success")), "bad": (theme.c("danger_soft"), theme.c("danger")),
                  "warn": (theme.c("accent_soft"), "#9A6511"), "muted": (theme.c("surface_alt"), theme.c("muted")),
                  "info": (theme.c("nav_active"), theme.c("primary") if theme.mode() == "light" else theme.c("text"))}
        bg, fg = colors.get(state, colors["muted"])
        self.setText(text)
        self.setStyleSheet(f"background:{bg}; color:{fg};")


class BarChart(QWidget):
    """Simple, crisp bar chart in the style of the NomFabric dashboard."""

    def __init__(self, parent=None, stacked_colors: list[str] | None = None, value_fmt="{:.0f}"):
        super().__init__(parent)
        self.labels: list[str] = []
        self.series: list[list[float]] = []
        self.colors = stacked_colors
        self.value_fmt = value_fmt
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_text = _("No data yet")

    def set_data(self, labels: list[str], *series: list[float]):
        self.labels = list(labels)
        self.series = [list(s) for s in series] or [[]]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        muted = QColor(theme.c("muted"))
        grid = QColor(theme.c("border"))
        totals = [sum(s[i] for s in self.series) for i in range(len(self.labels))] if self.series and self.labels else []
        if not totals or max(totals) <= 0:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        vmax = max(totals)
        step = _nice_step(vmax)
        top = step * int(np.ceil(vmax / step))
        left, right, tb, bb = 40, 10, 12, 40
        ch = h - tb - bb
        cw = w - left - right
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        v = 0.0
        while v <= top + 1e-9:
            y = tb + ch - ch * v / top
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(left, y), QPointF(w - right, y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self.value_fmt.format(v))
            v += step
        n = len(self.labels)
        slot = cw / n
        bw = min(56.0, slot * 0.6)
        colors = self.colors or [theme.c("chart")]
        for i, lab in enumerate(self.labels):
            x = left + slot * i + (slot - bw) / 2
            base = tb + ch
            for si, s in enumerate(self.series):
                val = s[i] if i < len(s) else 0
                if val <= 0:
                    continue
                bh = ch * val / top
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(colors[si % len(colors)]))
                p.drawRect(QRectF(x, base - bh, bw, bh))
                base -= bh
            p.setPen(muted)
            txt = lab if len(lab) <= 14 or slot > 110 else lab[:12] + "…"
            p.drawText(QRectF(left + slot * i, tb + ch + 4, slot, 32), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       txt)


def _nice_step(vmax: float) -> float:
    raw = vmax / 5
    mag = 10 ** np.floor(np.log10(max(raw, 1e-9)))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return max(m * mag, 1.0 if vmax >= 5 else m * mag)
    return 10 * mag


class VideoView(QLabel):
    """Shows BGR frames scaled to fit while keeping aspect ratio."""
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background:{theme.c('video_bg')}; border-radius: 10px; color: #9AA5BC;")
        self._img: QImage | None = None
        self.setText(_("No video"))

    def set_frame(self, frame: np.ndarray | None, message: str = ""):
        if frame is None:
            self._img = None
            self.setPixmap(QPixmap())
            self.setText(message or _("No video"))
            return
        self._img = bgr_to_qimage(frame)
        self._refresh()

    def _refresh(self):
        if self._img is None:
            return
        pm = QPixmap.fromImage(self._img).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()

    def heightForWidth(self, w):
        return int(w * 9 / 16)

    def sizeHint(self):
        return QSize(640, 360)


class Toast(QFrame):
    """Banner shown at the top of the content area for alerts."""
    acknowledged = Signal(int)

    def __init__(self, alert: dict, parent=None):
        super().__init__(parent)
        sev = alert.get("severity", "warning")
        bg = {"critical": theme.c("danger"), "warning": theme.c("accent"), "info": theme.c("success")}.get(sev, theme.c("info"))
        fg = "#1B2A4E" if sev == "warning" else "#FFFFFF"
        self.setStyleSheet(f"QFrame {{ background:{bg}; border-radius:10px; }} QLabel {{ color:{fg}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 8, 8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("bell", fg, 22))
        lay.addWidget(ic)
        t = QLabel(f"<b>{alert.get('title', '')}</b> &nbsp; {alert.get('message', '')}")
        t.setWordWrap(True)
        lay.addWidget(t, 1)
        ok = QPushButton(_("Acknowledge") if sev == "critical" else _("Dismiss"))
        ok.setStyleSheet(f"background: rgba(255,255,255,0.85); color:#1B2A4E; border:none; font-weight:600;")
        ok.clicked.connect(lambda: (self.acknowledged.emit(alert.get("id", 0)), self.deleteLater()))
        lay.addWidget(ok)
        if sev == "info":
            QTimer.singleShot(8000, self.deleteLater)


def make_table(headers: list[str], stretch_col: int | None = None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels([_(h) for h in headers])
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setShowGrid(False)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_col is not None:
        hh.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    else:
        hh.setStretchLastSection(True)
    t.verticalHeader().setDefaultSectionSize(38)
    return t


def fill_table(t: QTableWidget, rows: list[list], data: list | None = None, colors: dict | None = None):
    t.setRowCount(0)
    t.setRowCount(len(rows))
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            it = QTableWidgetItem("" if v is None else str(v))
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if colors and (i, j) in colors:
                it.setForeground(QColor(colors[(i, j)]))
                f = it.font(); f.setBold(True); it.setFont(f)
            if data is not None and j == 0:
                it.setData(Qt.ItemDataRole.UserRole, data[i])
            t.setItem(i, j, it)


def selected_data(t: QTableWidget):
    r = t.currentRow()
    if r < 0:
        return None
    it = t.item(r, 0)
    return it.data(Qt.ItemDataRole.UserRole) if it else None


def info(parent, text: str, title: str = "NomLoad"):
    QMessageBox.information(parent, title, text)


def error(parent, text: str, title: str = "NomLoad"):
    QMessageBox.warning(parent, title, text)


def confirm(parent, text: str, title: str = "NomLoad") -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


def logo_pixmap(size: int) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer

    from nomload.config import assets_dir
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    svg = (assets_dir() / "logo.svg").read_text()
    if theme.mode() == "dark":
        svg = svg.replace("#1B2A4E", "#E8ECF4").replace("#3E5A94", "#9AA5BC")
    from PySide6.QtCore import QByteArray
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


def rounded_pixmap(pm: QPixmap, radius: int = 8) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out

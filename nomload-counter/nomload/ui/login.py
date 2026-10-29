"""Login screen and splash screen."""
from __future__ import annotations

import random

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QLabel, QLineEdit, QPushButton, QSplashScreen,
                               QVBoxLayout, QWidget)

from nomload import APP_SHORT, VENDOR, __version__
from nomload.i18n import _
from nomload.services.context import AuthError
from nomload.ui.widgets import logo_pixmap

NAVY = QColor("#1B2A4E")
NAVY_D = QColor("#15213F")
NAVY_L = QColor("#22335D")
AMBER = QColor("#B9823A")
AMBER_L = QColor("#D29A4A")


def paint_pattern(p: QPainter, w: int, h: int, seed: int = 7):
    """Warehouse stack pattern: rows of cartons, a few 'detected' amber ones."""
    p.fillRect(0, 0, w, h, NAVY_D)
    bw, bh = 140, 70
    rng = random.Random(seed)
    for row in range(-1, h // bh + 2):
        off = (row % 2) * bw / 2
        for col in range(-1, w // bw + 2):
            x, y = col * bw + off, row * bh
            r = QRectF(x + 4, y + 4, bw - 8, bh - 8)
            p.setPen(Qt.PenStyle.NoPen)
            shade = NAVY if (row + col) % 3 else NAVY_L
            p.setBrush(shade)
            p.drawRoundedRect(r, 6, 6)
            # carton tape + subtle edge lines
            p.setBrush(QColor(255, 255, 255, 10))
            p.drawRect(QRectF(x + bw / 2 - 5, y + 4, 10, bh - 8))
            p.setPen(QPen(QColor(255, 255, 255, 14), 1))
            for k in range(1, 4):
                p.drawLine(int(x + 10), int(y + 4 + k * (bh - 8) / 4), int(x + bw / 2 - 12), int(y + 4 + k * (bh - 8) / 4))
    # scattered amber 'counted' items, some inside viewfinder brackets
    for i in range(14):
        x = rng.randint(0, max(1, w - 60))
        y = rng.randint(0, max(1, h - 60))
        if w * 0.33 < x < w * 0.66 and h * 0.12 < y < h * 0.85:
            continue
        s = 44
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRectF(x + 3, y + 4, s, s * 0.8), 6, 6)
        g = QLinearGradient(x, y, x, y + s)
        g.setColorAt(0, AMBER_L)
        g.setColorAt(1, AMBER)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(x, y, s, s * 0.8), 6, 6)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRect(QRectF(x + s / 2 - 3, y, 6, s * 0.8))
        if i % 3 == 0:
            p.setPen(QPen(QColor(255, 255, 255, 150), 3))
            m, L = 20, 16
            x0, y0, x1, y1 = x - m, y - m, x + s + m, y + s * 0.8 + m
            for (cx, cy, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
                p.drawLine(int(cx), int(cy), int(cx + dx * L), int(cy))
                p.drawLine(int(cx), int(cy), int(cx), int(cy + dy * L))


class LoginScreen(QWidget):
    logged_in = Signal(object)

    def __init__(self, app_services, parent=None):
        super().__init__(parent)
        self.app = app_services
        self._bg: QPixmap | None = None
        card = QFrame(self)
        card.setObjectName("LoginCard")
        card.setFixedWidth(520)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(60)
        sh.setOffset(0, 12)
        sh.setColor(QColor(0, 0, 0, 120))
        card.setGraphicsEffect(sh)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(52, 44, 52, 40)
        lay.setSpacing(6)
        logo = QLabel()
        from nomload import theme
        mode = theme.mode()
        theme.set_mode("light")
        logo.setPixmap(logo_pixmap(96))
        theme.set_mode(mode)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        name = QLabel(APP_SHORT)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 38px; font-weight: 800; color: #1B2A4E; margin-top: 8px;")
        lay.addWidget(name)
        sub = QLabel("C O U N T E R")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size: 13px; color: #5A6475; letter-spacing: 3px;")
        lay.addWidget(sub)
        self.company = QLabel(self.app.settings.get("company_name") or "")
        self.company.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.company.setStyleSheet("color: #3A4356; font-size: 15px; margin: 8px 0 18px 0;")
        lay.addWidget(self.company)
        for label, attr, echo in ((_("Username"), "user", False), (_("Password"), "pw", True)):
            l = QLabel(label)
            l.setStyleSheet("font-size: 15px; margin-top: 8px;")
            lay.addWidget(l)
            e = QLineEdit()
            e.setPlaceholderText(label)
            e.setMinimumHeight(48)
            if echo:
                e.setEchoMode(QLineEdit.EchoMode.Password)
            setattr(self, attr, e)
            lay.addWidget(e)
        self.msg = QLabel("")
        self.msg.setStyleSheet("color: #D64545; min-height: 22px;")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.btn = QPushButton(_("Log in"))
        self.btn.setMinimumHeight(54)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setStyleSheet("QPushButton { background:#1B2A4E; color:white; border:none; border-radius:10px;"
                               " font-size:17px; font-weight:700; } QPushButton:hover { background:#26386A; }")
        lay.addWidget(self.btn)
        self.card = card
        self.footer = QLabel(f"v{__version__} · {VENDOR}", self)
        self.footer.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent;")
        self.btn.clicked.connect(self._login)
        self.pw.returnPressed.connect(self._login)
        self.user.returnPressed.connect(lambda: self.pw.setFocus())

    def showEvent(self, e):
        super().showEvent(e)
        self.company.setText(self.app.settings.get("company_name") or "")
        self.user.setFocus()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg = None
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2, max(20, (self.height() - self.card.height()) // 2 - 10))
        self.footer.adjustSize()
        self.footer.move((self.width() - self.footer.width()) // 2, self.height() - 34)

    def paintEvent(self, e):
        if self._bg is None or self._bg.size() != self.size():
            self._bg = QPixmap(self.size())
            p = QPainter(self._bg)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            paint_pattern(p, self.width(), self.height())
            p.end()
        QPainter(self).drawPixmap(0, 0, self._bg)

    def _login(self):
        try:
            u = self.app.auth.login(self.user.text().strip(), self.pw.text())
        except AuthError as ex:
            self.msg.setText(str(ex))
            self.pw.selectAll()
            self.pw.setFocus()
            return
        self.msg.setText("")
        self.pw.clear()
        self.logged_in.emit(u)


def make_splash() -> QSplashScreen:
    w, h = 640, 360
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_pattern(p, w, h, seed=3)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(QRectF(150, 60, 340, 240), 18, 18)
    from nomload import theme
    mode = theme.mode()
    theme.set_mode("light")
    p.drawPixmap(270, 78, logo_pixmap(100))
    theme.set_mode(mode)
    f = QFont()
    f.setPixelSize(34)
    f.setBold(True)
    p.setFont(f)
    p.setPen(NAVY)
    p.drawText(QRectF(150, 180, 340, 44), Qt.AlignmentFlag.AlignCenter, APP_SHORT)
    f.setPixelSize(12)
    f.setBold(False)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
    p.setFont(f)
    p.setPen(QColor("#5A6475"))
    p.drawText(QRectF(150, 222, 340, 20), Qt.AlignmentFlag.AlignCenter, "COUNTER")
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
    f.setPixelSize(11)
    p.setFont(f)
    p.drawText(QRectF(150, 262, 340, 20), Qt.AlignmentFlag.AlignCenter, f"v{__version__} · {VENDOR}")
    p.end()
    sp = QSplashScreen(pm)
    return sp

"""Login screen (teal pattern background + logo card), first-run welcome/setup and session lock."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from app.__version__ import APP_NAME, APP_TAGLINE, __version__
from app.ui import brand
from app.ui.icons import icon
from app.ui.reusable_widgets import guarded, muted
from app.ui.theme import palette


class PatternBackground(QWidget):
    """Deep teal with a quiet grid of loyalty cards; a few carry the gold star."""
    CELL = 92

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def resizeEvent(self, ev):
        self._cache = None
        super().resizeEvent(ev)

    def paintEvent(self, ev):
        dpr = self.devicePixelRatioF()
        if self._cache is None or self._cache.size() != self.size() * dpr:
            self._cache = self._render(self.width(), self.height(), dpr)
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.end()

    def _render(self, w, h, dpr) -> QPixmap:
        pm = QPixmap(int(max(w, 1) * dpr), int(max(h, 1) * dpr))
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(QRectF(0, 0, w, h), QColor("#073C42"))
        c = self.CELL
        cx, cy = w / 2, h / 2
        for j in range(-1, h // c + 2):
            for i in range(-1, w // c + 2):
                x = i * c + (c / 2 if j % 2 else 0)
                y = j * c * 0.72
                card = QRectF(x + 10, y + 12, c - 20, (c - 20) * 0.62)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 13 if (i + j) % 3 else 22))
                p.drawRoundedRect(card, 7, 7)
                p.setBrush(QColor(255, 255, 255, 18))
                p.drawRect(QRectF(card.x(), card.y() + card.height() * 0.25, card.width(), 5))
                if (i * 7 + j * 11) % 23 == 0 and (abs(card.center().x() - cx) > 280 or abs(card.center().y() - cy) > 240):
                    _star(p, card.center(), 11, QColor(brand.GOLD))
        g = QRadialGradient(QPointF(cx, cy), max(w, h) * 0.75)
        g.setColorAt(0.0, QColor(4, 30, 34, 120))
        g.setColorAt(0.5, QColor(4, 30, 34, 60))
        g.setColorAt(1.0, QColor(2, 16, 20, 190))
        p.fillRect(QRectF(0, 0, w, h), g)
        p.end()
        return pm


def _star(p: QPainter, c: QPointF, r: float, color: QColor):
    path = QPainterPath()
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pt = QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a))
        path.moveTo(pt) if k == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.fillPath(path, color)


class _PasswordEye:
    def __init__(self, edit: QLineEdit):
        self.edit = edit
        edit.setEchoMode(QLineEdit.Password)
        self.action = edit.addAction(QIcon(), QLineEdit.TrailingPosition)
        self.action.setCheckable(True)
        self.action.toggled.connect(self._toggled)
        self._toggled(False)

    def _toggled(self, show: bool):
        self.edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        self.action.setIcon(icon("eye_off" if show else "eye", palette()["muted"], 18))
        self.action.setToolTip("Hide password" if show else "Show password")


class LoginPage(PatternBackground):
    logged_in = Signal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self); outer.setContentsMargins(16, 16, 16, 12)
        self.card = QFrame(); self.card.setObjectName("loginCard"); self.card.setFixedWidth(400)
        sh = QGraphicsDropShadowEffect(self.card); sh.setBlurRadius(60); sh.setOffset(0, 18)
        sh.setColor(QColor(0, 0, 0, 130)); self.card.setGraphicsEffect(sh)
        c = QVBoxLayout(self.card); c.setContentsMargins(40, 34, 40, 30); c.setSpacing(10)
        logo = QLabel(); logo.setAlignment(Qt.AlignHCenter); logo.setPixmap(brand.mark_pixmap(72))
        self.name = QLabel(); self.name.setAlignment(Qt.AlignHCenter); self.name.setTextFormat(Qt.RichText)
        sub = muted(APP_TAGLINE); sub.setAlignment(Qt.AlignHCenter)
        self.store = muted(""); self.store.setAlignment(Qt.AlignHCenter)
        self.user = QLineEdit(); self.user.setPlaceholderText("Username")
        self.pw = QLineEdit(); self.pw.setPlaceholderText("Password")
        self.eye = _PasswordEye(self.pw)
        self.msg = QLabel(); self.msg.setWordWrap(True); self.msg.setStyleSheet("color:#C2483A;"); self.msg.hide()
        self.btn = QPushButton("Sign in"); self.btn.setObjectName("primary"); self.btn.setMinimumHeight(38)
        self.btn.clicked.connect(self._login)
        self.pw.returnPressed.connect(self._login)
        self.user.returnPressed.connect(self.pw.setFocus)
        for w in (logo, self.name, sub, self.store):
            c.addWidget(w)
        c.addSpacing(10)
        for w in (self.user, self.pw, self.msg, self.btn):
            c.addWidget(w)
        ver = muted(f"{APP_NAME} {__version__} · Devnom"); ver.setAlignment(Qt.AlignHCenter)
        c.addSpacing(4); c.addWidget(ver)
        outer.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(self.card); row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def reset(self):
        self.name.setText(brand.wordmark_html(22, dark=False))
        store = self.ctx.settings.get("store_name") or ""
        self.store.setText(store); self.store.setVisible(bool(store))
        self.pw.clear(); self.msg.hide()
        (self.pw if self.user.text() else self.user).setFocus()

    def _login(self):
        from app.security.authentication import AuthError
        try:
            self.ctx.auth.login(self.user.text(), self.pw.text())
        except AuthError as exc:
            self.msg.setText(str(exc)); self.msg.show()
            self.pw.selectAll(); self.pw.setFocus()
            return
        self.pw.clear()
        self.logged_in.emit()


class FirstRunDialog(QDialog):
    """Welcome screen: store profile + the first Admin account (no default passwords exist)."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 22, 26, 20); lay.setSpacing(10)
        head = QHBoxLayout()
        lg = QLabel(); lg.setPixmap(brand.mark_pixmap(52)); head.addWidget(lg)
        t = QLabel(brand.wordmark_html(20)); t.setTextFormat(Qt.RichText); head.addWidget(t); head.addStretch(1)
        lay.addLayout(head)
        lay.addWidget(muted("Set up your store and create the administrator account. You can change the store "
                            "details later in Store settings."))
        f = QFormLayout(); f.setSpacing(8)
        self.store, self.address, self.phone = QLineEdit(), QLineEdit(), QLineEdit()
        self.currency = QLineEdit("PKR"); self.symbol = QLineEdit("Rs")
        self.username, self.full = QLineEdit(), QLineEdit()
        self.p1, self.p2 = QLineEdit(), QLineEdit()
        _PasswordEye(self.p1); _PasswordEye(self.p2)
        self.demo = QCheckBox("Load sample (demo) data so I can try the app - removable later")
        f.addRow("Store name *", self.store); f.addRow("Address", self.address); f.addRow("Phone", self.phone)
        cur = QHBoxLayout(); cur.addWidget(self.currency); cur.addWidget(QLabel("Symbol")); cur.addWidget(self.symbol)
        f.addRow("Currency", cur)
        f.addRow(QLabel(""))
        f.addRow("Admin username *", self.username); f.addRow("Full name", self.full)
        f.addRow("Password *", self.p1); f.addRow("Repeat password *", self.p2)
        lay.addLayout(f)
        lay.addWidget(muted("Password: at least 8 characters with letters and numbers."))
        lay.addWidget(self.demo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Create store"); bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        from PySide6.QtWidgets import QMessageBox
        if len(self.store.text().strip()) < 2:
            QMessageBox.warning(self, "Setup", "Enter the store name."); return
        if self.p1.text() != self.p2.text():
            QMessageBox.warning(self, "Setup", "The passwords do not match."); return
        ok, _ = guarded(self, "Setup", self.ctx.auth.create, self.username.text(), self.p1.text(), "Admin",
                        self.full.text(), None, True)
        if not ok:
            return
        s = self.ctx.settings
        s.set("store_name", self.store.text().strip()); s.set("store_address", self.address.text().strip())
        s.set("store_phone", self.phone.text().strip())
        s.set("currency_code", self.currency.text().strip().upper() or "PKR")
        s.set("currency_symbol", self.symbol.text().strip() or "Rs")
        from app import money
        money.CURRENCY.update(code=s.get("currency_code"), symbol=s.get("currency_symbol"))
        self.load_demo = self.demo.isChecked()
        self.admin = (self.username.text().strip(), self.p1.text())
        self.accept()


class LockDialog(QDialog):
    """Session lock: the same user unlocks with the password, or signs out."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.signed_out = False
        self.setWindowTitle("Locked")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 24, 28, 20); lay.setSpacing(10)
        lg = QLabel(); lg.setPixmap(brand.mark_pixmap(48)); lg.setAlignment(Qt.AlignHCenter)
        lay.addWidget(lg)
        lay.addWidget(QLabel(f"<b>{APP_NAME} is locked</b>"), alignment=Qt.AlignHCenter)
        lay.addWidget(muted(f"Signed in as {ctx.user.display}. Enter your password to continue."))
        self.pw = QLineEdit(); self.pw.setPlaceholderText("Password"); _PasswordEye(self.pw)
        self.msg = QLabel(); self.msg.setStyleSheet("color:#C2483A;")
        lay.addWidget(self.pw); lay.addWidget(self.msg)
        row = QHBoxLayout()
        out = QPushButton("Sign out"); out.clicked.connect(self._out)
        ok = QPushButton("Unlock"); ok.setObjectName("primary"); ok.clicked.connect(self._unlock)
        row.addWidget(out); row.addStretch(1); row.addWidget(ok)
        lay.addLayout(row)
        self.pw.returnPressed.connect(self._unlock)

    def _unlock(self):
        if self.ctx.auth.verify_current(self.pw.text()):
            self.accept()
        else:
            self.msg.setText("Wrong password."); self.pw.clear()

    def _out(self):
        self.signed_out = True
        self.accept()

    def reject(self):        # Esc does not unlock
        pass

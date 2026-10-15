"""Main window: login screen, sidebar navigation (NomFabric style) and pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from nomload import APP_NAME, APP_SHORT, __version__, theme
from nomload.config import assets_dir
from nomload.i18n import _
from nomload.services.context import ROLE_LABELS, audit
from nomload.ui import icons
from nomload.ui.dialogs import AlertsDialog, ChangePasswordDialog
from nomload.ui.login import LoginScreen
from nomload.ui.pages.common import QtBridge, SoundPlayer
from nomload.ui.widgets import Toast, logo_pixmap

NAV = [  # key, label, icon, permission
    ("dashboard", "Dashboard", "dashboard", None),
    ("live", "Live Bays", "live", "run_sessions"),
    ("sessions", "Sessions", "sessions", "run_sessions"),
    ("history", "History", "history", "view_history"),
    ("reports", "Reports", "reports", "view_reports"),
    ("products", "Products", "products", "manage_products"),
    ("cameras", "Cameras", "cameras", "manage_cameras"),
    ("training", "Training", "training", "manage_training"),
    ("users", "Users", "users", "manage_users"),
    ("settings", "Settings", "settings", "manage_settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(QIcon(str(assets_dir() / "app.ico")))
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.bridge = QtBridge()
        self.sound = SoundPlayer(app.settings, self)
        app.alerts.listeners.append(self.bridge.on_alert)
        self.bridge.alert.connect(self._on_alert)
        self.root = QStackedWidget()
        self.setCentralWidget(self.root)
        self.login = LoginScreen(app)
        self.login.logged_in.connect(self._logged_in)
        self.root.addWidget(self.login)
        self.shell = None
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lic_lbl = QLabel()
        sb.addWidget(self.lic_lbl)
        self.model_lbl = QLabel()
        sb.addPermanentWidget(self.model_lbl)
        self.queue_lbl = QLabel()
        sb.addPermanentWidget(self.queue_lbl)
        self.alert_btn = QPushButton()
        self.alert_btn.setFlat(True)
        self.alert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.alert_btn.setStyleSheet("border:none; padding: 2px 10px;")
        self.alert_btn.clicked.connect(lambda: (AlertsDialog(self, self.app).exec(), self.refresh_status()))
        sb.addPermanentWidget(self.alert_btn)
        self.refresh_status()
        t = QTimer(self)
        t.timeout.connect(self.refresh_status)
        t.start(15000)

    # ------------------------------------------------------------- shell
    def _build_shell(self):
        if self.shell is not None:
            self.root.removeWidget(self.shell)
            self.shell.deleteLater()
        u = self.app.user
        shell = QWidget()
        h = QHBoxLayout(shell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(270)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 22, 14, 14)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(logo_pixmap(52))
        brand.addWidget(lg)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        n = QLabel(APP_SHORT)
        n.setObjectName("BrandName")
        s = QLabel(_("Counter"))
        s.setObjectName("BrandSub")
        bt.addWidget(n)
        bt.addWidget(s)
        brand.addLayout(bt)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(18)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.nav_group = QButtonGroup(self)
        self.pages = {}
        self.nav_buttons = {}
        from nomload.ui.pages.cameras import CamerasPage
        from nomload.ui.pages.dashboard import DashboardPage
        from nomload.ui.pages.history import HistoryPage
        from nomload.ui.pages.live import LiveBaysPage
        from nomload.ui.pages.products import ProductsPage
        from nomload.ui.pages.reports import ReportsPage
        from nomload.ui.pages.sessions import SessionsPage
        from nomload.ui.pages.settings import SettingsPage
        from nomload.ui.pages.training import TrainingPage
        from nomload.ui.pages.users import UsersPage
        classes = {"dashboard": DashboardPage, "live": LiveBaysPage, "sessions": SessionsPage, "history": HistoryPage,
                   "reports": ReportsPage, "products": ProductsPage, "cameras": CamerasPage, "training": TrainingPage,
                   "users": UsersPage, "settings": SettingsPage}
        for key, label, ic, perm in NAV:
            if perm and not u.can(perm):
                # supervisors may view products; clerks see products read-only? keep it simple: hide
                continue
            b = QPushButton("  " + _(label))
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            sl.addWidget(b)
            page = classes[key](self)
            idx = self.stack.addWidget(page)
            self.pages[key] = page
            self.nav_buttons[key] = b
            self.nav_group.addButton(b, idx)
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)
        sl.addStretch(1)
        un = QLabel(u.display)
        un.setObjectName("UserName")
        ur = QLabel(ROLE_LABELS[u.role])
        ur.setObjectName("UserRole")
        sl.addWidget(un)
        sl.addWidget(ur)
        sl.addSpacing(10)
        for text, ic, fn in ((_("Appearance"), "moon", self.toggle_theme),
                             (_("Change password"), "lock", self.change_password),
                             (_("Log out"), "logout", self.logout)):
            b = QPushButton("  " + text)
            b.setObjectName("Link")
            b.setIcon(icons.icon(ic, theme.c("muted")))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            sl.addWidget(b)
        h.addWidget(side)
        right = QWidget()
        right.setObjectName("Content")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.toasts = QVBoxLayout()
        self.toasts.setContentsMargins(24, 8, 24, 0)
        self.toasts.setSpacing(6)
        rl.addLayout(self.toasts)
        rl.addWidget(self.stack, 1)
        h.addWidget(right, 1)
        self.shell = shell
        self.root.addWidget(shell)
        self.root.setCurrentWidget(shell)
        start = "live" if "live" in self.pages and u.role == "clerk" else "dashboard"
        self.go(start)

    def go(self, key: str):
        if key in self.pages:
            self.nav_buttons[key].setChecked(True)
            self.stack.setCurrentWidget(self.pages[key])

    # ------------------------------------------------------------- login / logout
    def _logged_in(self, user):
        self.app.user = user
        if user.must_change_pw:
            d = ChangePasswordDialog(self, self.app, forced=True)
            if not d.exec():
                self.app.user = None
                return
        self.app.start_bays(self.bridge)
        self._build_shell()
        if "live" in self.pages:
            self.pages["live"].rebuild()
        self.refresh_status()
        st = self.app.license.status()
        if not st.usable:
            self.toast({"severity": "critical", "title": _("Licence"), "message": st.message + " - " +
                        _("activate under Settings → Licence.")})
        elif st.trial:
            self.toast({"severity": "warning", "title": _("Trial mode"),
                        "message": f"{st.days_left} {_('day(s) left. Reports carry a TRIAL watermark.')}"})

    def logout(self):
        audit(self.app.db, self.app.user, "logout", "user", self.app.user.id)
        self.app.stop_bays()
        self.app.user = None
        self.root.setCurrentWidget(self.login)

    def change_password(self):
        ChangePasswordDialog(self, self.app).exec()

    def toggle_theme(self):
        new = "dark" if theme.mode() == "light" else "light"
        theme.set_mode(new)
        self.app.settings.set("theme", new)
        icons._render.cache_clear()
        QApplication.instance().setStyleSheet(theme.stylesheet())
        current = next((k for k, p in self.pages.items() if p is self.stack.currentWidget()), "dashboard")
        self._build_shell()
        if "live" in self.pages:
            self.pages["live"].rebuild()
        self.go(current)

    # ------------------------------------------------------------- runtime control
    def restart_bays(self):
        if self.app.user is None:
            return
        self.app.start_bays(self.bridge)
        if "live" in self.pages:
            self.pages["live"].rebuild()
        self.refresh_status()

    def reload_models_and_bays(self):
        self.app.load_models()
        self.restart_bays()

    # ------------------------------------------------------------- alerts & status
    def toast(self, alert: dict):
        if self.shell is None:
            return
        t = Toast(alert)
        t.acknowledged.connect(lambda aid: aid and self.app.alerts.acknowledge(aid, self.app.user))
        self.toasts.insertWidget(0, t)
        while self.toasts.count() > 3:
            w = self.toasts.itemAt(self.toasts.count() - 1).widget()
            self.toasts.removeWidget(w)
            w.deleteLater()

    def _on_alert(self, alert: dict):
        if alert["kind"] in ("cleared", "session_released"):
            self.refresh_status()
            return
        self.toast(alert)
        if alert["severity"] == "critical" and alert["kind"] != "mismatch":
            self.sound.play("alarm")
        elif alert["severity"] == "warning":
            self.sound.play("beep")
        self.refresh_status()

    def refresh_status(self):
        st = self.app.license.status()
        self.lic_lbl.setText(st.label)
        det = self.app.registry.detector
        self.model_lbl.setText(f"{_('Model')}: {det.name}" + (" · GPU" if det and det.providers[0] != "CPUExecutionProvider"
                                                              else " · CPU") if det else "")
        q = self.app.alerts.pending_count()
        self.queue_lbl.setText(f"{q} {_('alert(s) in outbox')}" if q else "")
        n = self.app.db.scalar("SELECT COUNT(*) FROM alerts WHERE acknowledged_at IS NULL AND severity<>'info'") or 0
        self.alert_btn.setIcon(icons.icon("bell", theme.c("danger") if n else theme.c("muted")))
        self.alert_btn.setText(f" {n}" if n else "")

    def closeEvent(self, e):
        active = [rt for rt in self.app.runtimes.values() if rt.session_id]
        if active and self.app.user:
            from nomload.ui.widgets import confirm
            if not confirm(self, _("Trucks are still loading. Close NomLoad anyway? Sessions continue when you restart.")):
                e.ignore()
                return
        self.app.shutdown()
        e.accept()

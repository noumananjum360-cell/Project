"""Main window: FabriScan-style sidebar (collapses to an icon rail), pages, auto-lock, tray notifications."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from app.__version__ import APP_NAME, APP_TAGLINE, __version__
from app.ui import brand
from app.ui.icons import icon
from app.ui.login_window import FirstRunDialog, LockDialog, LoginPage
from app.ui.reusable_widgets import guarded, show_error
from app.ui.theme import palette, stylesheet

log = logging.getLogger(__name__)

NAV = [("dashboard", "Dashboard", "dashboard.view"), ("pos", "POS Billing", "pos.use"),
       ("customers", "Customers", "customers.view"), ("alerts", "Alerts", "alerts.view"),
       ("sales", "Sales & Refunds", "sales.view_own"), ("vip", "VIP Customers", "vip.view"),
       ("products", "Products", "products.view"), ("reports", "Analytics", "reports.view"),
       ("integrations", "Import & POS", "import.run"), ("camera", "Camera", "camera.view"),
       ("staff", "Staff", "staff.manage"), ("audit", "Audit Log", "audit.view"), ("backup", "Backup", "backup.manage"),
       ("privacy", "Privacy", "privacy.requests"), ("settings", "Store Settings", "settings.manage"),
       ("help", "Help & About", None)]
NO_SCROLL = {"pos", "customers", "sales", "alerts", "audit", "products"}   # pages that manage their own space


class _Activity(QObject):
    def __init__(self, mw):
        super().__init__(); self.mw = mw

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.MouseButtonPress, QEvent.KeyPress):
            self.mw.last_activity = time.monotonic()
        return False


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        brand.load_brand_font()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} - {APP_TAGLINE}")
        self.setWindowIcon(brand.app_icon())
        self.setMinimumSize(980, 620)
        self.pages: dict[str, QWidget] = {}
        self._wrappers: dict[str, QWidget] = {}
        self._compact = None
        self._manual_rail = None
        self.root = QStackedWidget(); self.setCentralWidget(self.root)
        self.login = LoginPage(ctx); self.login.logged_in.connect(self._after_login)
        self.root.addWidget(self.login)
        self._build_shell()
        self.last_activity = time.monotonic()
        self._act = _Activity(self); QApplication.instance().installEventFilter(self._act)
        self.idle = QTimer(self); self.idle.timeout.connect(self._check_idle); self.idle.start(15000)
        self.poll = QTimer(self); self.poll.timeout.connect(self.refresh_badges); self.poll.start(20000)
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+L"), self, self.lock)
        self._setup_tray()
        self.apply_theme()
        self.show_login()

    # ------------------------------------------------------------------ shell
    def _build_shell(self):
        self.shell = QWidget(); sh = QHBoxLayout(self.shell); sh.setContentsMargins(0, 0, 0, 0); sh.setSpacing(0)
        side = QWidget(); side.setObjectName("sidebar"); self.side = side
        sv = QVBoxLayout(side); sv.setContentsMargins(0, 16, 0, 12); sv.setSpacing(2)
        self.brand_mark = QLabel(); self.brand_mark.setFixedSize(34, 34)
        self.bname = QLabel(); self.bname.setTextFormat(Qt.RichText)
        self.bsub = QLabel(APP_TAGLINE); self.bsub.setObjectName("muted")
        btxt = QWidget(); bt = QVBoxLayout(btxt); bt.setContentsMargins(0, 0, 0, 0); bt.setSpacing(0)
        bt.addWidget(self.bname); bt.addWidget(self.bsub)
        self.brand_txt = btxt
        self.brand_row = QWidget(); br = QHBoxLayout(self.brand_row); br.setContentsMargins(18, 0, 8, 14); br.setSpacing(10)
        br.addWidget(self.brand_mark); br.addWidget(btxt); br.addStretch()
        sv.addWidget(self.brand_row)
        self.nav = QListWidget(); self.nav.setObjectName("nav"); self.nav.setIconSize(QSize(18, 18))
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.currentRowChanged.connect(self._nav_changed)
        sv.addWidget(self.nav, 1)
        # one account button with a menu keeps the sidebar short enough for 1366 x 768 screens
        self.user_btn = QPushButton(); self.user_btn.setObjectName("side"); self.user_btn.setIconSize(QSize(16, 16))
        self.user_btn.setCursor(Qt.PointingHandCursor)
        self.user_menu = QMenu(self)
        self.side_actions = {}
        for key, text, fn in (("theme", "Appearance (light / dark)", self.toggle_theme), ("lock", "Lock  (Ctrl+L)", self.lock),
                              ("key", "Change password", self.change_password), ("menu", "Collapse menu", self.toggle_rail),
                              (None, None, None), ("logout", "Log out", self.logout)):
            if key is None:
                self.user_menu.addSeparator(); continue
            a = self.user_menu.addAction(text); a.triggered.connect(lambda _c=False, f=fn: f())
            self.side_actions[key] = a
        self.user_btn.setMenu(self.user_menu)
        self.user_btn.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0; }")
        sv.addWidget(self.user_btn)
        self.side_btns: dict[str, QPushButton] = {}
        sh.addWidget(side)
        self.stack = QStackedWidget()
        cont = QWidget(); cont.setObjectName("page"); cl = QVBoxLayout(cont); cl.setContentsMargins(26, 20, 26, 12)
        cl.addWidget(self.stack)
        sh.addWidget(cont, 1)
        self.root.addWidget(self.shell)

    def _create_page(self, key: str) -> QWidget:
        c = self.ctx
        if key == "dashboard":
            from app.ui.dashboard_page import DashboardPage; return DashboardPage(c, self)
        if key == "pos":
            from app.ui.pos_page import PosPage; return PosPage(c, self)
        if key == "customers":
            from app.ui.customers_page import CustomersPage; return CustomersPage(c, self)
        if key == "alerts":
            from app.ui.alerts_page import AlertsPage; return AlertsPage(c, self)
        if key == "sales":
            from app.ui.sales_page import SalesPage; return SalesPage(c, self)
        if key == "vip":
            from app.ui.vip_page import VipPage; return VipPage(c, self)
        if key == "products":
            from app.ui.products_page import ProductsPage; return ProductsPage(c, self)
        if key == "reports":
            from app.ui.reports_page import ReportsPage; return ReportsPage(c, self)
        if key == "integrations":
            from app.ui.integrations_page import IntegrationsPage; return IntegrationsPage(c, self)
        if key == "camera":
            from app.ui.camera_settings_page import CameraPage; return CameraPage(c, self)
        if key == "staff":
            from app.ui.staff_page import StaffPage; return StaffPage(c, self)
        if key == "audit":
            from app.ui.audit_page import AuditPage; return AuditPage(c, self)
        if key == "backup":
            from app.ui.backup_page import BackupPage; return BackupPage(c, self)
        if key == "privacy":
            from app.ui.privacy_page import PrivacyPage; return PrivacyPage(c, self)
        if key == "settings":
            from app.ui.settings_page import SettingsPage; return SettingsPage(c, self)
        from app.ui.help_page import HelpPage; return HelpPage(c, self)

    def page(self, key: str) -> QWidget:
        if key not in self.pages:
            p = self._create_page(key)
            self.pages[key] = p
            if key in NO_SCROLL:
                wrap = p
            else:
                wrap = QScrollArea(); wrap.setWidgetResizable(True); wrap.setFrameShape(QFrame.NoFrame)
                wrap.setWidget(p)
            self._wrappers[key] = wrap
            self.stack.addWidget(wrap)
        return self.pages[key]

    def _nav_changed(self, row: int):
        if row < 0:
            return
        key = self.nav.item(row).data(Qt.UserRole)
        try:
            p = self.page(key)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Error", f"Could not open this page: {exc}", exc)
            return
        self.stack.setCurrentWidget(self._wrappers[key])
        if hasattr(p, "refresh"):
            ok, _ = guarded(self, "Error", p.refresh)

    def goto(self, key: str):
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)
                return self.pages.get(key)
        return None

    def open_customer(self, cid: int, alert_id: int | None = None):
        from app.ui.customer_detail_page import CustomerProfileDialog
        if alert_id:
            self.ctx.alerts.opened_profile(alert_id)
        CustomerProfileDialog(self.ctx, cid, self).exec()
        self.refresh_badges()

    # ------------------------------------------------------------------ session
    def show_login(self):
        self.statusBar().hide()
        if self.ctx.auth.needs_first_run():
            d = FirstRunDialog(self.ctx, self)
            if not d.exec():
                QTimer.singleShot(0, self.close)
                return
            self.ctx.auth.login(*d.admin)
            if d.load_demo:
                from app.services.demo_data import load_demo
                guarded(self, "Demo data", load_demo, self.ctx)
            self._after_login()
            return
        self.login.reset()
        self.root.setCurrentWidget(self.login)

    def _after_login(self):
        u = self.ctx.user
        self.nav.blockSignals(True)
        self.nav.clear()
        for key, label, perm in NAV:
            if perm is None or self.ctx.can(perm):
                it = QListWidgetItem(label); it.setData(Qt.UserRole, key); it.setData(Qt.UserRole + 1, label)
                self.nav.addItem(it)
        self.nav.blockSignals(False)
        self._compact = None
        self._apply_compact()
        self._tint()
        self.root.setCurrentWidget(self.shell)
        self.statusBar().show()
        self.refresh_badges()
        self.last_activity = time.monotonic()
        self.goto("pos" if u.role == "Cashier" else "dashboard")
        if u.must_change_password:
            QTimer.singleShot(200, lambda: self.change_password(forced=True))
        try:
            self.ctx.privacy.apply_retention(u) if self.ctx.can("privacy.manage") else None
        except Exception:  # noqa: BLE001
            log.exception("retention failed")

    def logout(self):
        pos = self.pages.get("pos")
        if pos is not None and getattr(pos, "has_cart", lambda: False)():
            if QMessageBox.question(self, "Log out", "The current bill is not finished. Discard it and log out?") \
                    != QMessageBox.Yes:
                return
        cam = self.pages.get("camera")
        if cam is not None and hasattr(cam, "stop"):
            cam.stop()
        self.ctx.auth.logout()
        for w in list(self._wrappers.values()):
            self.stack.removeWidget(w); w.deleteLater()
        self.pages.clear(); self._wrappers.clear()
        self.show_login()

    def lock(self):
        if self.ctx.user is None or self.root.currentWidget() is not self.shell:
            return
        from app.security.audit import audit
        audit(self.ctx.db, self.ctx.user, "session_locked", "staff", self.ctx.user.id)
        self.shell.setVisible(False)
        d = LockDialog(self.ctx, self)
        d.exec()
        self.shell.setVisible(True)
        self.last_activity = time.monotonic()
        if d.signed_out:
            self.logout()

    def _check_idle(self):
        mins = int(self.ctx.settings.get("auto_lock_minutes") or 0)
        if mins and self.ctx.user and self.root.currentWidget() is self.shell and \
                time.monotonic() - self.last_activity > mins * 60 and QApplication.activeModalWidget() is None:
            self.lock()

    def change_password(self, forced: bool = False):
        from app.ui.staff_page import ChangePasswordDialog
        d = ChangePasswordDialog(self.ctx, self, forced)
        if not d.exec() and forced:
            self.logout()

    # ------------------------------------------------------------------ alerts / tray
    def _setup_tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(brand.app_icon(), self)
            self.tray.setToolTip(APP_NAME)
            self.tray.messageClicked.connect(self._tray_clicked)
            self.tray.show()
        from app.integrations.notifications import TrayNotifier
        self.ctx.alerts.notifier = TrayNotifier(self.tray)
        self.ctx.alerts.listeners.append(lambda _aid: QTimer.singleShot(0, self.refresh_badges))

    def _tray_clicked(self):
        self.showNormal(); self.raise_(); self.activateWindow()
        if self.ctx.user:
            self.goto("alerts")

    def refresh_badges(self):
        if self.ctx.user is None:
            return
        n = self.ctx.alerts.open_count()
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == "alerts":
                label = "Alerts" + (f"  ({n})" if n else "")
                it.setData(Qt.UserRole + 1, label)
                if not self._compact:
                    it.setText(label)
                it.setToolTip(label)
        self._status()

    def _status(self):
        u = self.ctx.user
        if not u:
            return
        from app.services.demo_data import has_demo
        demo = "   ·   DEMO DATA LOADED (remove it in Store settings)" if has_demo(self.ctx.db) else ""
        store = self.ctx.settings.get("store_name") or ""
        self.statusBar().showMessage(f"{store}   ·   {u.display} ({u.role}){demo}")

    # ------------------------------------------------------------------ look
    def apply_theme(self):
        QApplication.instance().setStyleSheet(stylesheet(self.ctx.settings.get("theme") or "light"))
        self._tint()
        for p in self.pages.values():
            if hasattr(p, "on_theme"):
                p.on_theme()

    def _tint(self):
        p = palette()
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            it.setIcon(icon({"pos": "pos"}.get(it.data(Qt.UserRole), it.data(Qt.UserRole)), p["text"]))
        for key, a in self.side_actions.items():
            a.setIcon(icon(key, p["muted"]))
        self.user_btn.setIcon(icon("staff", p["muted"]))
        dark = p["bg"].lower() != "#f6f8f8"
        self.brand_mark.setPixmap(brand.mark_pixmap(34, fg="#3CC7C2" if dark else brand.TEAL))
        self.bname.setText(brand.wordmark_html(15, dark))
        self._user_text()

    def _user_text(self):
        u = self.ctx.user
        if u:
            label = f"{u.display} · {u.role}  ▾"
            self.user_btn.setProperty("label", label)
            self.user_btn.setText("" if self._compact else label)
            self.user_btn.setToolTip(f"{u.display} ({u.role}) - account menu")

    def toggle_theme(self):
        s = self.ctx.settings
        s.set("theme", "dark" if (s.get("theme") or "light") == "light" else "light")
        self.apply_theme()

    def toggle_rail(self):
        self._manual_rail = not bool(self._compact)
        self._compact = None
        self._apply_compact()

    def _apply_compact(self):
        compact = self._manual_rail if self._manual_rail is not None else self.width() < 1240
        if compact == self._compact:
            return
        self._compact = compact
        self.side.setFixedWidth(64 if compact else 222)
        self.brand_txt.setVisible(not compact)
        self.brand_row.layout().setContentsMargins(15 if compact else 18, 0, 8, 14)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            label = it.data(Qt.UserRole + 1) or it.text()
            it.setText("" if compact else label)
            it.setToolTip(label if compact else "")
        self.side_actions["menu"].setText("Expand menu" if compact else "Collapse menu")
        self._user_text()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._manual_rail is None:
            self._apply_compact()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def fit_to_screen(self):
        st = QSettings("Devnom", "NomLoyal")
        geo = st.value("geometry")
        if geo is not None and self.restoreGeometry(geo):
            self.showMaximized() if st.value("maximized", False) in (True, "true") else self.show()
            return
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is None or scr.width() < 1500 or scr.height() < 900:
            self.showMaximized()
            return
        w, h = int(scr.width() * 0.86), int(scr.height() * 0.86)
        self.resize(w, h)
        self.move(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2)
        self.show()

    def closeEvent(self, ev):
        pos = self.pages.get("pos")
        if pos is not None and getattr(pos, "has_cart", lambda: False)():
            if QMessageBox.question(self, "Exit", "The current bill is not finished. Discard it and exit?") \
                    != QMessageBox.Yes:
                ev.ignore(); return
        cam = self.pages.get("camera")
        if cam is not None and hasattr(cam, "stop"):
            cam.stop()
        st = QSettings("Devnom", "NomLoyal")
        st.setValue("maximized", self.isMaximized())
        if not self.isMaximized() and not self.isFullScreen():
            st.setValue("geometry", self.saveGeometry())
        if self.ctx.user:
            self.ctx.auth.logout()
        if self.tray:
            self.tray.hide()
        ev.accept()

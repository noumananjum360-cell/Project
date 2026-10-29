"""Help, diagnostics and About."""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.__version__ import APP_NAME, APP_TAGLINE, VENDOR, __version__
from app.config import data_home, db_path, logs_dir
from app.ui import brand
from app.ui.reusable_widgets import PageHeader, button, card, info, muted, open_path, subtitle

GUIDE = [
    ("Sell", "POS Billing: scan or search products, link the customer (loyalty ID, QR card, phone or Select), "
             "then Complete sale (F9). Totals are always calculated by NomLoyal from the catalogue prices."),
    ("Register a customer", "Customers → Register customer. Show the privacy notice and tick the consent box. "
                            "Print the loyalty card (QR) from the profile."),
    ("Returning customers", "At the door or the till, scan the QR card or type the loyalty ID / phone in Alerts → "
                            "Front-desk check-in. Managers get an alert and can open the profile."),
    ("VIP", "Tiers are calculated automatically from valid purchases (VIP Customers → Tier rules). Refunds lower "
            "spending; voided sales do not count. Managers can override a tier with a reason."),
    ("Refunds", "Sales & Refunds → open the sale → Refund items. Choose the quantity of each item."),
    ("Import", "Import & POS → download a template, fill it, import. Check the preview before importing."),
    ("Backups", "Backup → Back up now. Copy backups to another safe place regularly."),
]


class HelpPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        lay.addWidget(PageHeader("Help & About"))
        g = card(subtitle("Quick guide"))
        for t, d in GUIDE:
            l = QLabel(f"<b>{t}</b> - {d}"); l.setWordWrap(True); l.setTextFormat(Qt.RichText)
            g.layout().addWidget(l)
        lay.addWidget(g)
        self.diag = QLabel(); self.diag.setTextFormat(Qt.RichText); self.diag.setWordWrap(True)
        self.diag.setTextInteractionFlags(Qt.TextSelectableByMouse)
        d = card(subtitle("Diagnostics"), self.diag)
        chk = button("Check database", icon_name="check"); chk.clicked.connect(self.check_db)
        logs = button("Open log folder"); logs.clicked.connect(lambda: open_path(logs_dir()))
        data = button("Open data folder"); data.clicked.connect(lambda: open_path(data_home()))
        for b in (chk, logs, data):
            d.layout().addWidget(b, alignment=Qt.AlignLeft)
        lay.addWidget(d)
        about = card(subtitle("About"))
        logo = QLabel(); logo.setPixmap(brand.mark_pixmap(56))
        about.layout().addWidget(logo)
        about.layout().addWidget(QLabel(brand.wordmark_html(18)))
        about.layout().addWidget(muted(f"{APP_TAGLINE} · version {__version__} · © {VENDOR}\nBiometric recognition is not "
                                       "included. Any recognition provider must be added, validated and used with "
                                       "explicit customer consent."))
        lay.addWidget(about)
        lay.addStretch(1)

    def refresh(self):
        import PySide6
        try:
            import cv2
            cv = cv2.__version__
        except Exception:  # noqa: BLE001
            cv = "not available (camera features disabled)"
        from app.migrations import SCHEMA_VERSION
        n = self.ctx.db.scalar
        self.diag.setText(
            f"Version {__version__} · Python {sys.version.split()[0]} · PySide6 {PySide6.__version__} · OpenCV {cv}<br>"
            f"Windows/OS: {platform.platform()}<br>Database: {db_path()} (schema {SCHEMA_VERSION})<br>"
            f"Customers {n('SELECT COUNT(*) FROM customers')} · products {n('SELECT COUNT(*) FROM products')} · "
            f"sales {n('SELECT COUNT(*) FROM sales')} · staff {n('SELECT COUNT(*) FROM staff_users')}<br>"
            f"Logs: {logs_dir()}")

    def check_db(self):
        ok = self.ctx.db.integrity_ok()
        info(self, "Database", "The database is healthy." if ok else
             "The integrity check found a problem. Restore the latest backup and contact support.")

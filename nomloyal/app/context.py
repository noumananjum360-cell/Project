"""Wires the database, security and services together (one instance per running app)."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app import money
from app.config import db_path, logs_dir
from app.database import Database
from app.repositories.settings_repo import Settings
from app.security.authentication import AuthService
from app.services.alert_service import AlertService
from app.services.backup_service import BackupService
from app.services.customer_service import CustomerService
from app.services.import_service import ImportService
from app.services.privacy_service import PrivacyService
from app.services.product_service import ProductService
from app.services.reporting_service import ReportingService
from app.services.sales_service import SalesService
from app.services.vip_service import VipService


class _NoSecrets(logging.Filter):
    def filter(self, record):
        msg = str(record.getMessage()).lower()
        return not any(w in msg for w in ("password=", "passwd", "token="))


def setup_logging() -> Path:
    path = logs_dir() / "nomloyal.log"
    root = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        h = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        h.addFilter(_NoSecrets())
        root.addHandler(h)
        root.setLevel(logging.INFO)
    return path


class AppContext:
    def __init__(self, path: str | Path | None = None):
        self.db = Database(path or db_path())
        self.settings = Settings(self.db)
        money.CURRENCY.update(code=self.settings.get("currency_code"), symbol=self.settings.get("currency_symbol"))
        self.auth = AuthService(self.db, self.settings)
        self.vip = VipService(self.db, self.auth, self.settings)
        self.alerts = AlertService(self.db, self.auth, self.settings)
        self.customers = CustomerService(self.db, self.auth, self.settings, self.vip, self.alerts)
        self.products = ProductService(self.db, self.auth)
        self.sales = SalesService(self.db, self.auth, self.settings, self.products, self.vip)
        self.reports = ReportingService(self.db, self.auth)
        self.privacy = PrivacyService(self.db, self.auth, self.settings, self.vip)
        self.backup = BackupService(self.db, self.auth)
        self.imports = ImportService(self.db, self.auth, self.settings, self.customers, self.products, self.vip)

    @property
    def user(self):
        return self.auth.user

    def can(self, perm: str) -> bool:
        return self.auth.can(perm)

    def close(self):
        self.db.close()

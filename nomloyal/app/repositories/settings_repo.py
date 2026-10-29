"""Key/value store settings (JSON values) with defaults."""
from __future__ import annotations

import json
import threading
import time

DEFAULTS: dict = {
    # store
    "store_name": "",
    "store_address": "",
    "store_phone": "",
    "currency_code": "PKR",
    "currency_symbol": "Rs",
    "tax_rate_bp": 0,                    # default sales tax (basis points) - products may override
    "tax_label": "Sales tax",
    "receipt_prefix": "INV",
    "receipt_footer": "Thank you for shopping with us.",
    "payment_methods": ["Cash", "Card", "Bank transfer", "Mobile wallet"],
    "max_discount_pct_cashier": 10,      # cashier may give at most this discount (percent of the sale)
    "void_same_day_only": True,
    # loyalty / VIP
    "loyalty_id_prefix": "NL",
    "manager_can_edit_vip_rules": False,
    "refund_policy": "subtract",         # refunds reduce net spending and can lower the tier
    # alerts & notifications
    "alerts_enabled": True,
    "alert_returning_after_days": 1,     # a returning visit = first visit after this many days
    "alert_dedup_minutes": 30,
    "os_notifications": True,
    # privacy & retention
    "privacy_notice_version": "1.0",
    "retention_visits_days": 365,
    "retention_alerts_days": 180,
    "retention_inactive_customer_months": 0,   # 0 = never auto-anonymize
    "require_data_consent": True,
    # camera / recognition (biometric recognition is OFF by default)
    "camera_source": "",
    "camera_kind": "usb",
    "camera_fps": 10,
    "camera_width": 960,
    "recognition_enabled": False,
    "recognition_provider": "none",
    "recognition_threshold": 0.8,
    "recognition_require_confirmation": True,
    # integrations
    "pos_import_folder": "",
    # security / UI
    "auto_lock_minutes": 10,
    "theme": "light",
    "demo_data_loaded": False,
}


class Settings:
    def __init__(self, db):
        self.db = db
        self._lock = threading.Lock()
        self._cache: dict = {}
        for r in db.q("SELECT key, value FROM app_settings"):
            try:
                self._cache[r["key"]] = json.loads(r["value"])
            except (TypeError, ValueError):
                pass

    def get(self, key: str, default=None):
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT INTO app_settings(key, value, updated_at) VALUES (?,?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (key, json.dumps(value), time.time()))
        with self._lock:
            self._cache[key] = value

    def all(self) -> dict:
        out = dict(DEFAULTS)
        with self._lock:
            out.update(self._cache)
        return out

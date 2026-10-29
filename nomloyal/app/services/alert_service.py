"""In-app alert centre with duplicate prevention and privacy-preserving OS notifications."""
from __future__ import annotations

import logging
import time

from app.security.audit import audit
from app.services.errors import NotFound

log = logging.getLogger(__name__)

# the ONLY text that ever leaves the app (Windows notification): no names, no purchases
OS_TITLE = "NomLoyal"
OS_MESSAGE = "Registered loyalty customer detected. Open NomLoyal to review the customer profile."


class AlertService:
    def __init__(self, db, auth, settings):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.notifier = None          # callable(title, message) set by the UI (system tray)
        self.listeners: list = []     # callables(alert_id) for live UI updates

    def returning_customer(self, cust, method: str, simulated: bool = False) -> int | None:
        if not self.settings.get("alerts_enabled"):
            return None
        window = float(self.settings.get("alert_dedup_minutes") or 0) * 60
        dup = self.db.scalar("SELECT id FROM alerts WHERE customer_id=? AND kind='returning_customer' AND created_at>=?",
                             (cust.id, time.time() - window))
        if dup:
            return None
        src = {"loyalty_id": "Loyalty ID", "phone": "Phone lookup", "qr": "QR code", "selected": "Cashier selection",
               "recognition": "Recognition provider"}.get(method, method)
        title = "Returning customer" + (f" - {cust.tier}" if cust.tier else "")
        if simulated:
            title = "[DEMO - SIMULATED] " + title
        elif cust.is_demo:
            title = "[DEMO] " + title
        msg = (f"Registered loyalty customer identified by {src}. Open the profile to review." if not simulated else
               "SIMULATED match for demonstration only - no camera recognition took place.")
        now = time.time()
        aid = self.db.execute("INSERT INTO alerts(kind, customer_id, title, message, source, is_simulated, created_at, "
                              "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                              ("returning_customer", cust.id, title, msg, method, int(simulated), now, now))
        self._notify_os(aid)
        for fn in list(self.listeners):
            try:
                fn(aid)
            except Exception:  # noqa: BLE001 - a UI listener must never break the alert
                log.exception("alert listener failed")
        return aid

    def _notify_os(self, aid: int):
        if not self.settings.get("os_notifications") or self.notifier is None:
            return
        try:
            self.notifier(OS_TITLE, OS_MESSAGE)
            self.db.execute("UPDATE alerts SET os_notified=1 WHERE id=?", (aid,))
        except Exception as exc:  # noqa: BLE001
            log.warning("OS notification failed: %s", exc)
            self.db.execute("UPDATE alerts SET os_error=? WHERE id=?", (str(exc)[:200], aid))

    def list(self, status: str | None = "open", limit: int = 300) -> list[dict]:
        self.auth.require("alerts.view")
        sql = ("SELECT a.*, c.full_name customer, c.loyalty_id, COALESCE(c.vip_override_tier, c.vip_tier) tier, "
               "u.username handled_by_name FROM alerts a LEFT JOIN customers c ON c.id=a.customer_id "
               "LEFT JOIN staff_users u ON u.id=a.handled_by")
        args = []
        if status:
            sql += " WHERE a.status=?"; args.append(status)
        return [dict(r) for r in self.db.q(sql + " ORDER BY a.created_at DESC LIMIT ?", (*args, limit))]

    def open_count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM alerts WHERE status='open'", default=0))

    def handle(self, aid: int, status: str):
        user = self.auth.require("alerts.handle")
        if status not in ("acknowledged", "dismissed"):
            raise ValueError(status)
        if not self.db.scalar("SELECT 1 FROM alerts WHERE id=?", (aid,)):
            raise NotFound("Alert not found.")
        now = time.time()
        self.db.execute("UPDATE alerts SET status=?, handled_by=?, handled_at=?, updated_at=? WHERE id=?",
                        (status, user.id or None, now, now, aid))
        audit(self.db, user, f"alert_{status}", "alert", aid)

    def opened_profile(self, aid: int):
        user = self.auth.require("alerts.view")
        audit(self.db, user, "alert_profile_opened", "alert", aid)

"""Consent, data export, correction, deletion/anonymisation and retention."""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from pathlib import Path

from app.security.audit import audit
from app.services.errors import NotFound, ValidationError

CONSENT_TYPES = {"data_processing": "Store and use customer details", "marketing": "Marketing messages",
                 "biometric": "Biometric recognition (optional)"}


class PrivacyService:
    def __init__(self, db, auth, settings, vip=None):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.vip = vip

    # ------------------------------------------------------------------ consent
    def consent_status(self, cid: int) -> dict[str, bool]:
        out = {}
        for t in CONSENT_TYPES:
            r = self.db.one("SELECT granted FROM consent_records WHERE customer_id=? AND consent_type=? "
                            "ORDER BY recorded_at DESC, id DESC LIMIT 1", (cid, t))
            out[t] = bool(r and r["granted"])
        return out

    def consent_history(self, cid: int) -> list[dict]:
        self.auth.require("customers.view_sensitive")
        return [dict(r) for r in self.db.q("SELECT c.*, u.username recorded_by_name FROM consent_records c "
                                           "LEFT JOIN staff_users u ON u.id=c.recorded_by WHERE customer_id=? "
                                           "ORDER BY recorded_at DESC, c.id DESC", (cid,))]

    def record_consent(self, cid: int, consent_type: str, granted: bool, method: str = "in_store", notes: str = ""):
        user = self.auth.require("customers.edit")
        if consent_type not in CONSENT_TYPES:
            raise ValidationError("Unknown consent type.")
        if consent_type == "biometric" and granted and self.settings.get("recognition_provider") in ("", "none"):
            raise ValidationError("No recognition provider is configured, so biometric consent cannot be recorded.")
        self.db.execute("INSERT INTO consent_records(customer_id, consent_type, granted, notice_version, method, "
                        "recorded_by, recorded_at, notes) VALUES (?,?,?,?,?,?,?,?)",
                        (cid, consent_type, int(granted), self.settings.get("privacy_notice_version"), method,
                         user.id or None, time.time(), notes))
        audit(self.db, user, "consent_granted" if granted else "consent_withdrawn", "customer", cid,
              {"type": consent_type})

    # ------------------------------------------------------------------ export
    def export_customer(self, cid: int, out: str | Path) -> Path:
        user = self.auth.require("customers.export")
        c = self.db.one("SELECT * FROM customers WHERE id=?", (cid,))
        if c is None:
            raise NotFound("Customer not found.")
        data = {
            "customer": {k: c[k] for k in c.keys() if k not in ("vip_override_by",)},
            "consent": [dict(r) for r in self.db.q("SELECT consent_type, granted, notice_version, method, recorded_at "
                                                   "FROM consent_records WHERE customer_id=? ORDER BY recorded_at", (cid,))],
            "visits": [dict(r) for r in self.db.q("SELECT visited_at, method FROM customer_visits WHERE customer_id=? "
                                                  "ORDER BY visited_at", (cid,))],
            "sales": [], "refunds": [],
        }
        for s in self.db.q("SELECT * FROM sales WHERE customer_id=? ORDER BY sold_at", (cid,)):
            sd = {k: s[k] for k in ("receipt_no", "sold_at", "subtotal", "discount_total", "tax_total", "total",
                                    "payment_method", "status")}
            sd["items"] = [dict(r) for r in self.db.q("SELECT sku, name, category, qty, unit_price, line_total, refunded_qty "
                                                      "FROM sale_items WHERE sale_id=?", (s["id"],))]
            data["sales"].append(sd)
            data["refunds"] += [dict(r) for r in self.db.q("SELECT refund_no, refunded_at, amount, reason FROM refunds "
                                                           "WHERE sale_id=?", (s["id"],))]
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("customer_data.json", json.dumps(data, indent=2, ensure_ascii=False, default=str))
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["receipt_no", "date", "item", "qty", "line_total_minor", "status"])
            for s in data["sales"]:
                for it in s["items"]:
                    w.writerow([s["receipt_no"], time.strftime("%Y-%m-%d %H:%M", time.localtime(s["sold_at"])),
                                it["name"], it["qty"], it["line_total"], s["status"]])
            z.writestr("purchases.csv", buf.getvalue())
            z.writestr("README.txt", "Personal data held by the store about this customer, exported from NomLoyal.\n"
                                     "Amounts are in minor currency units (paisa).\n")
        audit(self.db, user, "customer_data_exported", "customer", cid, {"file": out.name})
        return out

    # ------------------------------------------------------------------ delete / anonymise
    def delete_customer(self, cid: int, reason: str) -> str:
        """Hard-delete a customer without sales; otherwise anonymise (sales stay for the store's accounts,
        but no longer identify the person). Returns 'deleted' or 'anonymized'."""
        user = self.auth.require("customers.delete")
        if not reason.strip():
            raise ValidationError("Enter the reason (for example: customer request).")
        c = self.db.one("SELECT loyalty_id, status FROM customers WHERE id=?", (cid,))
        if c is None:
            raise NotFound("Customer not found.")
        has_sales = self.db.scalar("SELECT COUNT(*) FROM sales WHERE customer_id=?", (cid,))
        now = time.time()
        with self.db.tx() as cx:
            cx.execute("DELETE FROM customer_visits WHERE customer_id=?", (cid,))
            cx.execute("UPDATE alerts SET customer_id=NULL, title='Customer data deleted', message='' WHERE customer_id=?",
                       (cid,))
            if has_sales:
                cx.execute("UPDATE customers SET full_name=?, phone=NULL, email='', notes='', tags='', status='anonymized', "
                           "vip_tier=NULL, vip_reason='', vip_override_tier=NULL, vip_override_reason='', "
                           "updated_at=? WHERE id=?", (f"Deleted customer #{cid}", now, cid))
                cx.execute("INSERT INTO consent_records(customer_id, consent_type, granted, notice_version, method, "
                           "recorded_by, recorded_at, notes) VALUES (?,?,0,?,?,?,?,?)",
                           (cid, "data_processing", self.settings.get("privacy_notice_version"), "deletion",
                            user.id or None, now, "Data deleted"))
                result = "anonymized"
            else:
                cx.execute("DELETE FROM consent_records WHERE customer_id=?", (cid,))
                cx.execute("DELETE FROM customers WHERE id=?", (cid,))
                result = "deleted"
        audit(self.db, user, f"customer_{result}", "customer", cid, {"loyalty_id": c["loyalty_id"], "reason": reason})
        return result

    # ------------------------------------------------------------------ retention
    def apply_retention(self, actor=None) -> dict:
        """Delete old visits/alerts and (optionally) anonymise long-inactive customers."""
        s = self.settings
        now = time.time()
        out = {"visits": 0, "alerts": 0, "customers": 0}
        vd = int(s.get("retention_visits_days") or 0)
        if vd:
            out["visits"] = self.db.conn().execute("SELECT COUNT(*) FROM customer_visits WHERE visited_at<?",
                                                   (now - vd * 86400,)).fetchone()[0]
            self.db.execute("DELETE FROM customer_visits WHERE visited_at<?", (now - vd * 86400,))
        ad = int(s.get("retention_alerts_days") or 0)
        if ad:
            out["alerts"] = self.db.conn().execute("SELECT COUNT(*) FROM alerts WHERE created_at<? AND status<>'open'",
                                                   (now - ad * 86400,)).fetchone()[0]
            self.db.execute("DELETE FROM alerts WHERE created_at<? AND status<>'open'", (now - ad * 86400,))
        months = int(s.get("retention_inactive_customer_months") or 0)
        if months:
            cutoff = now - months * 30.44 * 86400
            old = self.db.q("SELECT c.id FROM customers c WHERE c.status<>'anonymized' AND c.updated_at<? AND NOT EXISTS "
                            "(SELECT 1 FROM sales s WHERE s.customer_id=c.id AND s.sold_at>=?) AND NOT EXISTS "
                            "(SELECT 1 FROM customer_visits v WHERE v.customer_id=c.id AND v.visited_at>=?)",
                            (cutoff, cutoff, cutoff))
            if old:
                prev = self.auth.user
                try:
                    from app.security.authentication import SYSTEM
                    self.auth.user = actor or prev or SYSTEM
                    for r in old:
                        self.delete_customer(r["id"], f"retention: inactive for {months} months")
                        out["customers"] += 1
                finally:
                    self.auth.user = prev
        audit(self.db, actor or self.auth.user, "retention_applied", "privacy", "", out)
        return out

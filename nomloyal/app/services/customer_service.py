"""Customer CRM: register, edit, archive, look up (loyalty ID / phone / QR / selection) and check in."""
from __future__ import annotations

import re
import time

from app.models import Customer
from app.repositories.customers_repo import CustomersRepo
from app.security.audit import audit
from app.services.errors import NotFound, ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(phone: str) -> str:
    """'0300-1234567', '+92 300 1234567', '923001234567' -> '03001234567'. Empty stays empty."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    if not 7 <= len(digits) <= 15:
        raise ValidationError("Phone number must have 7 to 15 digits.")
    return digits


def luhn_digit(num: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def valid_loyalty_id(lid: str) -> bool:
    m = re.fullmatch(r"([A-Z]{1,4})-?(\d{6})(\d)", lid.strip().upper())
    return bool(m and luhn_digit(m.group(2)) == m.group(3))


class CustomerService:
    def __init__(self, db, auth, settings, vip=None, alerts=None):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.repo = CustomersRepo(db)
        self.vip = vip
        self.alerts = alerts

    # ------------------------------------------------------------------ helpers
    def _new_loyalty_id(self, c) -> str:
        prefix = (self.settings.get("loyalty_id_prefix") or "NL").upper()[:4]
        n = (c.execute("SELECT COALESCE(MAX(id), 0) FROM customers").fetchone()[0] or 0) + 1
        while True:
            body = f"{n:06d}"
            lid = f"{prefix}-{body}{luhn_digit(body)}"
            if not c.execute("SELECT 1 FROM customers WHERE loyalty_id=?", (lid,)).fetchone():
                return lid
            n += 1

    def _validate(self, name: str, phone: str, email: str) -> tuple[str, str, str]:
        name = " ".join((name or "").split())
        if len(name) < 2:
            raise ValidationError("Enter the customer's name.")
        if len(name) > 120:
            raise ValidationError("Name is too long.")
        phone = normalize_phone(phone)
        email = (email or "").strip()
        if email and not EMAIL_RE.match(email):
            raise ValidationError("Email address is not valid.")
        return name, phone, email

    def get(self, cid: int) -> Customer:
        self.auth.require("customers.view")
        c = self.repo.get(cid)
        if c is None:
            raise NotFound("Customer not found.")
        return c

    # ------------------------------------------------------------------ create / edit
    def create(self, name: str, phone: str = "", email: str = "", notes: str = "", tags: str = "",
               data_consent: bool = False, marketing_consent: bool = False, is_demo: bool = False) -> Customer:
        user = self.auth.require("customers.create")
        name, phone, email = self._validate(name, phone, email)
        if self.settings.get("require_data_consent") and not data_consent and not is_demo:
            raise ValidationError("The customer's consent to store their details is required. "
                                  "Read the privacy notice to the customer and tick the consent box.")
        if phone and self.repo.by_phone(phone):
            raise ValidationError("A customer with this phone number already exists.")
        now = time.time()
        version = self.settings.get("privacy_notice_version")
        with self.db.tx() as c:
            lid = self._new_loyalty_id(c)
            cid = c.execute("INSERT INTO customers(loyalty_id, full_name, phone, email, notes, tags, is_demo, created_at, "
                            "updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                            (lid, name, phone or None, email, notes.strip(), _tags(tags), int(is_demo), now, now)).lastrowid
            for ctype, granted in (("data_processing", data_consent), ("marketing", marketing_consent)):
                c.execute("INSERT INTO consent_records(customer_id, consent_type, granted, notice_version, recorded_by, "
                          "recorded_at) VALUES (?,?,?,?,?,?)", (cid, ctype, int(bool(granted)), version, user.id, now))
        audit(self.db, user, "customer_created", "customer", cid, {"loyalty_id": lid})
        return self.repo.get(cid)

    def update(self, cid: int, name: str, phone: str, email: str, notes: str, tags: str) -> Customer:
        user = self.auth.require("customers.edit")
        cur = self.get(cid)
        if cur.status == "anonymized":
            raise ValidationError("This customer's data was deleted and cannot be edited.")
        name, phone, email = self._validate(name, phone, email)
        other = self.repo.by_phone(phone) if phone else None
        if other and other.id != cid:
            raise ValidationError("Another customer already has this phone number.")
        self.db.execute("UPDATE customers SET full_name=?, phone=?, email=?, notes=?, tags=?, updated_at=? WHERE id=?",
                        (name, phone or None, email, notes.strip(), _tags(tags), time.time(), cid))
        changed = [k for k, a, b in (("name", cur.full_name, name), ("phone", cur.phone, phone), ("email", cur.email, email),
                                     ("notes", cur.notes, notes.strip()), ("tags", cur.tags, _tags(tags))) if a != b]
        audit(self.db, user, "customer_updated", "customer", cid, {"fields": changed})
        return self.repo.get(cid)

    def set_archived(self, cid: int, archived: bool):
        user = self.auth.require("customers.archive")
        cur = self.get(cid)
        if cur.status == "anonymized":
            raise ValidationError("This customer's data was deleted.")
        self.db.execute("UPDATE customers SET status=?, archived_at=?, updated_at=? WHERE id=?",
                        ("archived" if archived else "active", time.time() if archived else None, time.time(), cid))
        audit(self.db, user, "customer_archived" if archived else "customer_restored", "customer", cid)

    # ------------------------------------------------------------------ search / lookup
    def search(self, text: str = "", status: str | None = "active", tier: str | None = None, limit: int = 500,
               offset: int = 0, order: str = "name") -> list[Customer]:
        self.auth.require("customers.view")
        return self.repo.search(text, status, tier, limit, offset, order)

    def lookup(self, value: str) -> tuple[Customer, str]:
        """Find a customer by loyalty ID, scanned QR text or phone. Returns (customer, method).
        Raises NotFound when nothing matches exactly - a sale is never linked on a guess."""
        self.auth.require("customers.view")
        v = (value or "").strip()
        if not v:
            raise NotFound("Enter a loyalty ID, scan the QR code or type the phone number.")
        if v.upper().startswith("NOMLOYAL:"):            # QR code on the loyalty card
            c = self.repo.by_loyalty_id(v.split(":", 1)[1])
            if c and c.status == "active":
                return c, "qr"
            raise NotFound("QR code not recognised.")
        if any(ch.isalpha() for ch in v):
            c = self.repo.by_loyalty_id(v.upper() if "-" in v else _insert_dash(v.upper()))
            if c and c.status == "active":
                return c, "loyalty_id"
            raise NotFound("No active customer with this loyalty ID.")
        try:
            phone = normalize_phone(v)
        except ValidationError:
            raise NotFound("No customer with this phone number.") from None
        c = self.repo.by_phone(phone)
        if c and c.status == "active":
            return c, "phone"
        raise NotFound("No customer with this phone number.")

    def check_in(self, cid: int, method: str, notes: str = "", simulated: bool = False) -> int | None:
        """Record a verified store visit. Returns the alert id when a returning-customer alert was raised."""
        user = self.auth.require("customers.view")
        cust = self.get(cid)
        now = time.time()
        last = self.db.scalar("SELECT MAX(t) FROM (SELECT MAX(visited_at) t FROM customer_visits WHERE customer_id=? "
                              "UNION ALL SELECT MAX(sold_at) FROM sales WHERE customer_id=? AND status<>'voided')",
                              (cid, cid))
        self.db.execute("INSERT INTO customer_visits(customer_id, visited_at, method, staff_id, notes, is_demo, created_at) "
                        "VALUES (?,?,?,?,?,?,?)", (cid, now, method, user.id, notes, int(cust.is_demo or simulated), now))
        audit(self.db, user, "customer_checked_in", "customer", cid, {"method": method, "simulated": simulated})
        gap = float(self.settings.get("alert_returning_after_days") or 0) * 86400
        if self.alerts and last and now - last >= gap:
            return self.alerts.returning_customer(cust, method, simulated=simulated)
        return None

    def qr_payload(self, cust: Customer) -> str:
        return f"NOMLOYAL:{cust.loyalty_id}"


def _tags(tags: str) -> str:
    parts = [t.strip() for t in (tags or "").replace(";", ",").split(",") if t.strip()]
    return ", ".join(dict.fromkeys(parts))


def _insert_dash(v: str) -> str:
    m = re.fullmatch(r"([A-Z]{1,4})(\d{7})", v)
    return f"{m.group(1)}-{m.group(2)}" if m else v

"""CSV import (preview -> commit) and export for customers, products and sales.

Every row is validated; duplicates are detected and skipped; nothing is written until the user commits the preview.
Imported sales are linked to a customer ONLY when the file carries a loyalty ID or phone number that exactly matches
an active customer. Imported sales are historical and do not change stock.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.money import fmt, rate_bp, to_minor
from app.security.audit import audit
from app.services.errors import ValidationError

TEMPLATES = {
    "customers": ["full_name", "phone", "email", "loyalty_id", "tags", "notes", "data_consent", "marketing_consent"],
    "products": ["sku", "name", "category", "unit_price", "tax_rate_percent", "stock_qty", "track_stock"],
    "sales": ["receipt_no", "sold_at", "customer_loyalty_id", "customer_phone", "sku", "qty", "unit_price",
              "line_discount", "payment_method", "reported_total"],
}
YES = {"yes", "y", "true", "1", "x"}


@dataclass
class RowResult:
    line: int
    status: str                  # ok | error | duplicate | warning
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class Preview:
    kind: str
    filename: str
    rows: list[RowResult] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)     # sales: one entry per receipt

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)


def read_csv(path: str | Path) -> list[dict]:
    p = Path(path)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(p, newline="", encoding=enc) as f:
                rd = csv.DictReader(f)
                return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in rd]
        except UnicodeDecodeError:
            continue
    raise ValidationError("The file is not a readable CSV (save it as CSV UTF-8).")


def write_template(kind: str, path: str | Path) -> Path:
    path = Path(path)
    examples = {
        "customers": ["Ayesha Khan", "0300-1234567", "ayesha@example.com", "", "saree, bridal", "Prefers silk", "yes", "no"],
        "products": ["SAR-001", "Banarasi silk saree", "Sarees", "18500", "0", "12", "yes"],
        "sales": ["POS-10001", "2026-10-01 14:30", "", "0300-1234567", "SAR-001", "1", "18500", "0", "Card", "18500"],
    }
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(TEMPLATES[kind])
        w.writerow(examples[kind])
    return path


class ImportService:
    def __init__(self, db, auth, settings, customers, products, vip):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.customers = customers
        self.products = products
        self.vip = vip

    # ------------------------------------------------------------------ preview
    def preview(self, kind: str, path: str | Path, rows: list[dict] | None = None) -> Preview:
        self.auth.require("import.run")
        if kind not in TEMPLATES:
            raise ValidationError("Unknown import type.")
        rows = rows if rows is not None else read_csv(path)
        if not rows:
            raise ValidationError("The file has no data rows.")
        missing = [c for c in TEMPLATES[kind][:2] if c not in rows[0]]
        if missing:
            raise ValidationError(f"Missing columns: {', '.join(missing)}. Use the template.")
        pv = Preview(kind, Path(str(path)).name)
        getattr(self, f"_preview_{kind}")(rows, pv)
        return pv

    def _preview_customers(self, rows, pv: Preview):
        from app.services.customer_service import EMAIL_RE, normalize_phone, valid_loyalty_id
        seen_phone, seen_lid = set(), set()
        for i, r in enumerate(rows, start=2):
            try:
                name = " ".join(r.get("full_name", "").split())
                if len(name) < 2:
                    raise ValidationError("full_name is required")
                phone = normalize_phone(r.get("phone", ""))
                email = r.get("email", "")
                if email and not EMAIL_RE.match(email):
                    raise ValidationError("email is not valid")
                lid = r.get("loyalty_id", "").upper()
                if lid and not valid_loyalty_id(lid):
                    raise ValidationError("loyalty_id is not a valid NomLoyal ID (leave empty to create one)")
                consent = r.get("data_consent", "").lower() in YES
                if self.settings.get("require_data_consent") and not consent:
                    raise ValidationError("data_consent must be 'yes' (the customer's consent to store their details)")
                if (phone and (phone in seen_phone or self.customers.repo.by_phone(phone))) or \
                        (lid and (lid in seen_lid or self.customers.repo.by_loyalty_id(lid))):
                    pv.rows.append(RowResult(i, "duplicate", f"{name}: phone or loyalty ID already exists"))
                    continue
                seen_phone.add(phone); seen_lid.add(lid)
                pv.rows.append(RowResult(i, "ok", name, {"name": name, "phone": phone, "email": email, "loyalty_id": lid,
                                                          "tags": r.get("tags", ""), "notes": r.get("notes", ""),
                                                          "data_consent": consent,
                                                          "marketing": r.get("marketing_consent", "").lower() in YES}))
            except ValidationError as e:
                pv.rows.append(RowResult(i, "error", str(e)))

    def _preview_products(self, rows, pv: Preview):
        seen = set()
        for i, r in enumerate(rows, start=2):
            try:
                sku, name = r.get("sku", ""), " ".join(r.get("name", "").split())
                if not sku or len(name) < 2:
                    raise ValidationError("sku and name are required")
                price = to_minor(r.get("unit_price", ""))
                tax = rate_bp(r["tax_rate_percent"]) if r.get("tax_rate_percent", "") != "" else None
                stock = int(r.get("stock_qty") or 0)
                data = {"sku": sku, "name": name, "category": r.get("category") or "General", "unit_price": price,
                        "tax_rate_bp": tax, "stock_qty": stock,
                        "track_stock": (r.get("track_stock", "yes").lower() or "yes") in YES}
                if sku.lower() in seen or self.products.by_sku(sku):
                    pv.rows.append(RowResult(i, "duplicate", f"SKU {sku} already exists", data))
                    continue
                seen.add(sku.lower())
                pv.rows.append(RowResult(i, "ok", f"{sku} {name} {fmt(price)}", data))
            except (ValidationError, ValueError, TypeError) as e:
                pv.rows.append(RowResult(i, "error", str(e)))

    def _preview_sales(self, rows, pv: Preview):
        from app.services.customer_service import normalize_phone
        from app.services.sales_service import price_lines
        groups: dict[str, dict] = {}
        for i, r in enumerate(rows, start=2):
            rno = r.get("receipt_no", "").strip().upper()
            try:
                if not rno:
                    raise ValidationError("receipt_no is required")
                g = groups.setdefault(rno, {"receipt_no": rno, "lines": [], "rows": [], "errors": [], "meta": r})
                g["rows"].append(i)
                p = self.products.by_sku(r.get("sku", ""))
                if p is None:
                    raise ValidationError(f"unknown SKU '{r.get('sku', '')}' - import products first")
                qty = int(r.get("qty") or 0)
                g["lines"].append({"product_id": p.id, "sku": p.sku, "name": p.name, "category": p.category, "qty": qty,
                                   "unit_price": to_minor(r.get("unit_price") or "0"),
                                   "line_discount": to_minor(r.get("line_discount") or "0"), "tax_rate_bp": p.tax_rate_bp})
            except (ValidationError, ValueError, TypeError) as e:
                if rno in groups:
                    groups[rno]["errors"].append(f"line {i}: {e}")
                pv.rows.append(RowResult(i, "error", str(e)))
        default_rate = int(self.settings.get("tax_rate_bp") or 0)
        methods = self.settings.get("payment_methods") or []
        for rno, g in groups.items():
            first = g["rows"][0]
            if g["errors"]:
                continue
            m = g["meta"]
            try:
                if self.db.scalar("SELECT 1 FROM sales WHERE receipt_no=?", (rno,)):
                    pv.rows.append(RowResult(first, "duplicate", f"{rno} was already imported"))
                    continue
                when = _parse_dt(m.get("sold_at", ""))
                pay = m.get("payment_method") or "Cash"
                if pay not in methods:
                    raise ValidationError(f"payment_method '{pay}' is not set up (Store settings)")
                q = price_lines(g["lines"], 0, default_rate)
                reported = m.get("reported_total", "")
                if reported and to_minor(reported) != q.total:
                    raise ValidationError(f"does not reconcile: file total {fmt(to_minor(reported))}, "
                                          f"calculated {fmt(q.total)}")
                cust, method, note = None, "none", "no customer"
                lid, phone = m.get("customer_loyalty_id", "").upper(), m.get("customer_phone", "")
                if lid:
                    c = self.customers.repo.by_loyalty_id(lid)
                    if c and c.status == "active":
                        cust, method, note = c.id, "pos_import", f"customer {c.loyalty_id}"
                    else:
                        note = "loyalty ID not found - imported without customer"
                elif phone:
                    try:
                        c = self.customers.repo.by_phone(normalize_phone(phone))
                    except ValidationError:
                        c = None
                    if c and c.status == "active":
                        cust, method, note = c.id, "pos_import", f"customer {c.loyalty_id}"
                    else:
                        note = "phone not found - imported without customer"
                g.update(quote=q, when=when, payment=pay, customer_id=cust, link=method)
                pv.groups.append(g)
                status = "ok" if cust or not (lid or phone) else "warning"
                pv.rows.append(RowResult(first, status, f"{rno}: {len(g['lines'])} item(s), {fmt(q.total)}, {note}"))
            except (ValidationError, ValueError) as e:
                pv.rows.append(RowResult(first, "error", f"{rno}: {e}"))
        pv.rows.sort(key=lambda r: r.line)

    # ------------------------------------------------------------------ commit
    def commit(self, pv: Preview) -> int:
        user = self.auth.require("import.run")
        now = time.time()
        errors = [f"line {r.line}: {r.message}" for r in pv.rows if r.status == "error"]
        job = self.db.execute("INSERT INTO import_jobs(kind, filename, rows_total, rows_error, rows_duplicate, errors_json, "
                              "user_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                              (pv.kind, pv.filename, len(pv.rows), len(errors), pv.count("duplicate"),
                               json.dumps(errors[:500]), user.id or None, now, now))
        n, touched = 0, set()
        try:
            with self.db.tx() as c:
                if pv.kind == "customers":
                    for r in pv.rows:
                        if r.status != "ok":
                            continue
                        d = r.data
                        if d["loyalty_id"]:
                            cid = c.execute("INSERT INTO customers(loyalty_id, full_name, phone, email, notes, tags, "
                                            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                                            (d["loyalty_id"], d["name"], d["phone"] or None, d["email"], d["notes"],
                                             d["tags"], now, now)).lastrowid
                        else:
                            lid = self.customers._new_loyalty_id(c)
                            cid = c.execute("INSERT INTO customers(loyalty_id, full_name, phone, email, notes, tags, "
                                            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                                            (lid, d["name"], d["phone"] or None, d["email"], d["notes"], d["tags"], now,
                                             now)).lastrowid
                        for ctype, granted in (("data_processing", d["data_consent"]), ("marketing", d["marketing"])):
                            c.execute("INSERT INTO consent_records(customer_id, consent_type, granted, notice_version, "
                                      "method, recorded_by, recorded_at, notes) VALUES (?,?,?,?,?,?,?,?)",
                                      (cid, ctype, int(granted), self.settings.get("privacy_notice_version"), "import",
                                       user.id or None, now, f"import job {job}"))
                        n += 1
                elif pv.kind == "products":
                    for r in pv.rows:
                        if r.status != "ok":
                            continue
                        d = r.data
                        c.execute("INSERT INTO products(sku, name, category, unit_price, tax_rate_bp, stock_qty, track_stock, "
                                  "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                  (d["sku"], d["name"], d["category"], d["unit_price"], d["tax_rate_bp"], d["stock_qty"],
                                   int(d["track_stock"]), now, now))
                        n += 1
                else:
                    from app.services.sales_service import SalesService
                    for g in pv.groups:
                        q = g["quote"]
                        sid = c.execute("INSERT INTO sales(receipt_no, customer_id, link_method, cashier_id, sold_at, "
                                        "subtotal, discount_total, tax_total, total, payment_method, source, import_job_id, "
                                        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                        (g["receipt_no"], g["customer_id"], g["link"], None, g["when"], q.subtotal,
                                         q.discount_total, q.tax_total, q.total, g["payment"], "import", job, now,
                                         now)).lastrowid
                        SalesService._insert_items(c, sid, q)
                        if g["customer_id"]:
                            touched.add(g["customer_id"])
                        n += 1
        except Exception as exc:
            self.db.execute("UPDATE import_jobs SET status='failed', errors_json=?, updated_at=? WHERE id=?",
                            (json.dumps(errors[:500] + [f"import failed: {exc}"]), time.time(), job))
            raise
        self.db.execute("UPDATE import_jobs SET status='completed', rows_ok=?, updated_at=? WHERE id=?",
                        (n, time.time(), job))
        audit(self.db, user, "import_completed", "import_job", job, {"kind": pv.kind, "imported": n,
                                                                      "errors": len(errors),
                                                                      "duplicates": pv.count("duplicate")})
        for cid in touched:
            self.vip.recalculate(cid, reason=f"import job {job}")
        return n

    def jobs(self, limit: int = 50) -> list[dict]:
        self.auth.require("import.run")
        return [dict(r) for r in self.db.q("SELECT j.*, u.username FROM import_jobs j LEFT JOIN staff_users u "
                                           "ON u.id=j.user_id ORDER BY j.created_at DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------------ export
    def export(self, kind: str, path: str | Path) -> int:
        """CSV export in the same format as the import templates (round-trip)."""
        user = self.auth.require("export.unrestricted" if kind == "customers" else "reports.export")
        path = Path(path)
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(TEMPLATES[kind])
            if kind == "customers":
                from app.services.privacy_service import PrivacyService
                ps = PrivacyService(self.db, self.auth, self.settings)
                for r in self.db.q("SELECT * FROM customers WHERE status='active' ORDER BY id"):
                    cs = ps.consent_status(r["id"])
                    w.writerow([r["full_name"], r["phone"] or "", r["email"], r["loyalty_id"], r["tags"], r["notes"],
                                "yes" if cs["data_processing"] else "no", "yes" if cs["marketing"] else "no"]); n += 1
            elif kind == "products":
                for r in self.db.q("SELECT * FROM products ORDER BY sku"):
                    w.writerow([r["sku"], r["name"], r["category"], _major(r["unit_price"]),
                                "" if r["tax_rate_bp"] is None else r["tax_rate_bp"] / 100, r["stock_qty"],
                                "yes" if r["track_stock"] else "no"]); n += 1
            else:
                for r in self.db.q("SELECT s.receipt_no, s.sold_at, s.payment_method, s.total, c.loyalty_id, c.phone, "
                                   "i.sku, i.qty, i.unit_price, i.line_discount FROM sales s JOIN sale_items i "
                                   "ON i.sale_id=s.id LEFT JOIN customers c ON c.id=s.customer_id "
                                   "WHERE s.status<>'voided' ORDER BY s.sold_at, i.id"):
                    w.writerow([r["receipt_no"], dt.datetime.fromtimestamp(r["sold_at"]).strftime("%Y-%m-%d %H:%M"),
                                r["loyalty_id"] or "", r["phone"] or "", r["sku"], r["qty"], _major(r["unit_price"]),
                                _major(r["line_discount"]), r["payment_method"], _major(r["total"])]); n += 1
        audit(self.db, user, "data_exported", kind, "", {"rows": n, "file": path.name})
        return n


def _major(minor: int) -> str:
    return f"{minor / 100:.2f}"


def _parse_dt(text: str) -> float:
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            d = dt.datetime.strptime(text.strip(), f)
            if d > dt.datetime.now() + dt.timedelta(minutes=5):
                raise ValidationError("sold_at is in the future")
            return d.timestamp()
        except ValueError:
            continue
    raise ValidationError(f"sold_at '{text}' - use YYYY-MM-DD HH:MM")

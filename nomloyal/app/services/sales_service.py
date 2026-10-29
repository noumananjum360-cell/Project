"""POS billing, refunds and voids. All money is integer minor units.

Pricing rules (documented, tested):
  gross            = qty x catalogue unit price
  line discount    = 0 .. gross (per line)
  invoice discount = 0 .. sum(gross - line discounts), shared across lines in proportion (largest remainder)
  tax              = (gross - line discount - invoice share) x rate, per line, rounded half-up
                     rate = product rate, or the store default when the product has none (prices are tax-exclusive)
  line total       = taxable + tax;  sale total = sum of line totals

Refund rules: a refunded unit returns its exact share of the line total (tax and discounts included); the last
unit returns the remainder so a full refund equals the amount paid. Refunds reduce the customer's net spending.
Voids: only sales without refunds; voided sales count for nothing.
"""
from __future__ import annotations

import datetime as dt
import time

from app.models import CartLine, PricedLine, Quote
from app.security.audit import audit
from app.security.permissions import PermissionDenied
from app.services.errors import NotFound, ValidationError

LINK_METHODS = ("none", "loyalty_id", "phone", "qr", "selected", "pos_import")


def split_proportional(amount: int, weights: list[int]) -> list[int]:
    """Split `amount` across `weights` so the parts add up exactly (largest-remainder method)."""
    total = sum(weights)
    if amount == 0 or total == 0:
        return [0] * len(weights)
    raw = [amount * w for w in weights]
    parts = [r // total for r in raw]
    rest = amount - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (raw[i] % total, weights[i]), reverse=True)
    for i in order[:rest]:
        parts[i] += 1
    return parts


def price_lines(items: list[dict], invoice_discount: int, default_rate_bp: int) -> Quote:
    """items: [{product_id, sku, name, category, qty, unit_price, line_discount, tax_rate_bp|None}]"""
    from app.money import pct_of
    if invoice_discount < 0:
        raise ValidationError("Discount cannot be negative.")
    nets = []
    for it in items:
        if not isinstance(it["qty"], int) or it["qty"] <= 0:
            raise ValidationError(f"Quantity for {it['name']} must be a whole number above zero.")
        if it["qty"] > 100000:
            raise ValidationError(f"Quantity for {it['name']} is too large.")
        gross = it["qty"] * it["unit_price"]
        if not 0 <= it["line_discount"] <= gross:
            raise ValidationError(f"Discount on {it['name']} cannot be more than the line amount.")
        nets.append(gross - it["line_discount"])
    if invoice_discount > sum(nets):
        raise ValidationError("Invoice discount cannot be more than the sale amount.")
    shares = split_proportional(invoice_discount, nets)
    q = Quote(invoice_discount=invoice_discount)
    for it, net, share in zip(items, nets, shares):
        rate = it["tax_rate_bp"] if it.get("tax_rate_bp") is not None else default_rate_bp
        taxable = net - share
        tax = pct_of(taxable, rate)
        q.lines.append(PricedLine(it.get("product_id"), it["sku"], it["name"], it["category"], it["qty"],
                                  it["unit_price"], it["line_discount"], share, rate, tax, taxable + tax))
    q.subtotal = sum(l.gross for l in q.lines)
    q.discount_total = sum(l.line_discount for l in q.lines) + invoice_discount
    q.tax_total = sum(l.line_tax for l in q.lines)
    q.total = sum(l.line_total for l in q.lines)
    return q


class SalesService:
    def __init__(self, db, auth, settings, products, vip=None):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.products = products
        self.vip = vip

    # ------------------------------------------------------------------ pricing
    def quote(self, cart: list[CartLine], invoice_discount: int = 0) -> Quote:
        if not cart:
            raise ValidationError("Add at least one product.")
        items = []
        for cl in cart:
            p = self.products.get(cl.product_id)
            if not p.active:
                raise ValidationError(f"{p.name} is not for sale (inactive).")
            items.append({"product_id": p.id, "sku": p.sku, "name": p.name, "category": p.category, "qty": cl.qty,
                          "unit_price": p.unit_price, "line_discount": int(cl.line_discount), "tax_rate_bp": p.tax_rate_bp})
        return price_lines(items, int(invoice_discount), int(self.settings.get("tax_rate_bp") or 0))

    def _check_discount_limit(self, q: Quote, user):
        if self.auth.can("sales.refund", user):        # managers and admins are not limited
            return
        limit = int(self.settings.get("max_discount_pct_cashier") or 0)
        if q.subtotal and q.discount_total * 100 > q.subtotal * limit:
            raise PermissionDenied(f"Discounts above {limit}% need a manager.")

    # ------------------------------------------------------------------ numbering
    def _next_no(self, c, table: str, col: str, prefix: str, when: float) -> str:
        day = dt.datetime.fromtimestamp(when).strftime("%Y%m%d")
        base = f"{prefix}-{day}-"
        last = c.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE ? ORDER BY {col} DESC LIMIT 1",
                         (base + "%",)).fetchone()
        n = int(last[0].rsplit("-", 1)[1]) + 1 if last else 1
        return f"{base}{n:04d}"

    # ------------------------------------------------------------------ sale
    def checkout(self, cart: list[CartLine], payment_method: str, customer_id: int | None = None,
                 link_method: str = "none", invoice_discount: int = 0, notes: str = "", sold_at: float | None = None,
                 is_demo: bool = False) -> int:
        user = self.auth.require("sales.create")
        if payment_method not in (self.settings.get("payment_methods") or []):
            raise ValidationError("Choose a payment method.")
        if link_method not in LINK_METHODS:
            raise ValidationError("Unknown customer link method.")
        if (customer_id is None) != (link_method == "none"):
            raise ValidationError("A customer must be linked through a loyalty ID, phone, QR code or selection.")
        if customer_id is not None:
            r = self.db.one("SELECT status FROM customers WHERE id=?", (customer_id,))
            if r is None or r["status"] != "active":
                raise ValidationError("The selected customer is not active.")
        q = self.quote(cart, invoice_discount)
        self._check_discount_limit(q, user)
        now = time.time()
        when = sold_at or now
        with self.db.tx() as c:
            for line in q.lines:                                  # stock check inside the transaction
                p = c.execute("SELECT name, stock_qty, track_stock FROM products WHERE id=?", (line.product_id,)).fetchone()
                if p["track_stock"] and p["stock_qty"] < line.qty and not is_demo:
                    raise ValidationError(f"Not enough stock for {p['name']} (in stock: {p['stock_qty']}).")
            receipt = self._next_no(c, "sales", "receipt_no", self.settings.get("receipt_prefix") or "INV", when)
            sid = c.execute("INSERT INTO sales(receipt_no, customer_id, link_method, cashier_id, sold_at, subtotal, "
                            "discount_total, tax_total, total, invoice_discount, payment_method, source, notes, is_demo, "
                            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (receipt, customer_id, link_method, user.id or None, when, q.subtotal, q.discount_total,
                             q.tax_total, q.total, q.invoice_discount, payment_method, "demo" if is_demo else "pos",
                             notes.strip(), int(is_demo), now, now)).lastrowid
            self._insert_items(c, sid, q)
            for line in q.lines:
                c.execute("UPDATE products SET stock_qty=stock_qty-?, updated_at=? WHERE id=? AND track_stock=1",
                          (line.qty, now, line.product_id))
            if customer_id:
                c.execute("INSERT INTO customer_visits(customer_id, visited_at, method, staff_id, notes, is_demo, created_at) "
                          "VALUES (?,?,?,?,?,?,?)", (customer_id, when, "purchase", user.id or None, receipt, int(is_demo), now))
        audit(self.db, user, "sale_completed", "sale", sid, {"receipt": receipt, "total": q.total,
                                                              "customer_id": customer_id, "link": link_method})
        if customer_id and self.vip:
            self.vip.recalculate(customer_id, reason=f"sale {receipt}")
        return sid

    @staticmethod
    def _insert_items(c, sid: int, q: Quote):
        for l in q.lines:
            c.execute("INSERT INTO sale_items(sale_id, product_id, sku, name, category, qty, unit_price, line_discount, "
                      "invoice_discount_share, tax_rate_bp, line_tax, line_total) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, l.product_id, l.sku, l.name, l.category, l.qty, l.unit_price, l.line_discount,
                       l.invoice_discount_share, l.tax_rate_bp, l.line_tax, l.line_total))

    # ------------------------------------------------------------------ read
    def get(self, sid: int) -> dict:
        s = self.db.one("SELECT s.*, c.full_name customer, c.loyalty_id, u.full_name cashier_name, u.username cashier "
                        "FROM sales s LEFT JOIN customers c ON c.id=s.customer_id "
                        "LEFT JOIN staff_users u ON u.id=s.cashier_id WHERE s.id=?", (sid,))
        if s is None:
            raise NotFound("Sale not found.")
        user = self.auth.require("sales.view_own")
        if not self.auth.can("sales.view_all") and s["cashier_id"] != user.id:
            raise PermissionDenied("You can only open your own sales.")
        out = dict(s)
        out["items"] = [dict(r) for r in self.db.q("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sid,))]
        out["refunds"] = [dict(r) for r in self.db.q(
            "SELECT r.*, u.username processed_by_name FROM refunds r LEFT JOIN staff_users u ON u.id=r.processed_by "
            "WHERE r.sale_id=? ORDER BY r.refunded_at", (sid,))]
        out["refunded_total"] = sum(r["amount"] for r in out["refunds"])
        return out

    def by_receipt(self, receipt_no: str) -> dict:
        r = self.db.one("SELECT id FROM sales WHERE receipt_no=?", ((receipt_no or "").strip().upper(),))
        if r is None:
            raise NotFound("No sale with this receipt number.")
        return self.get(r["id"])

    def search(self, t0: float | None = None, t1: float | None = None, text: str = "", status: str = "",
               customer_id: int | None = None, limit: int = 1000) -> list[dict]:
        user = self.auth.require("sales.view_own")
        where, args = [], []
        if not self.auth.can("sales.view_all"):
            where.append("s.cashier_id=?"); args.append(user.id)
        if t0 is not None:
            where.append("s.sold_at>=?"); args.append(t0)
        if t1 is not None:
            where.append("s.sold_at<?"); args.append(t1)
        if status:
            where.append("s.status=?"); args.append(status)
        if customer_id:
            where.append("s.customer_id=?"); args.append(customer_id)
        if text:
            where.append("(s.receipt_no LIKE ? OR c.full_name LIKE ? OR c.loyalty_id LIKE ?)"); args += [f"%{text}%"] * 3
        sql = ("SELECT s.id, s.receipt_no, s.sold_at, s.total, s.status, s.payment_method, s.is_demo, s.link_method, "
               "c.full_name customer, c.id customer_id, u.username cashier, "
               "(SELECT COALESCE(SUM(amount),0) FROM refunds r WHERE r.sale_id=s.id) refunded "
               "FROM sales s LEFT JOIN customers c ON c.id=s.customer_id LEFT JOIN staff_users u ON u.id=s.cashier_id"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY s.sold_at DESC LIMIT ?")
        return [dict(r) for r in self.db.q(sql, (*args, limit))]

    # ------------------------------------------------------------------ refunds
    def refund(self, sid: int, quantities: dict[int, int], reason: str, method: str = "Cash", restock: bool = True) -> int:
        user = self.auth.require("sales.refund")
        if not reason.strip():
            raise ValidationError("Enter the reason for the refund.")
        sale = self.db.one("SELECT * FROM sales WHERE id=?", (sid,))
        if sale is None:
            raise NotFound("Sale not found.")
        if sale["status"] == "voided":
            raise ValidationError("A voided sale cannot be refunded.")
        quantities = {int(k): int(v) for k, v in quantities.items() if int(v) > 0}
        if not quantities:
            raise ValidationError("Choose at least one item and quantity to refund.")
        now = time.time()
        with self.db.tx() as c:
            items = {r["id"]: r for r in c.execute("SELECT * FROM sale_items WHERE sale_id=?", (sid,)).fetchall()}
            plan, amount = [], 0
            for iid, qty in quantities.items():
                it = items.get(iid)
                if it is None:
                    raise ValidationError("That item is not part of this sale.")
                left = it["qty"] - it["refunded_qty"]
                if qty > left:
                    raise ValidationError(f"Only {left} x {it['name']} can still be refunded.")
                before = it["refunded_qty"]
                a = _unit_share(it["line_total"], it["qty"], before + qty) - _unit_share(it["line_total"], it["qty"], before)
                plan.append((it, qty, a))
                amount += a
            rno = self._next_no(c, "refunds", "refund_no", "RF", now)
            rid = c.execute("INSERT INTO refunds(refund_no, sale_id, processed_by, refunded_at, reason, amount, method, "
                            "restock, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (rno, sid, user.id or None, now, reason.strip(), amount, method, int(restock), now, now)).lastrowid
            for it, qty, a in plan:
                c.execute("INSERT INTO refund_items(refund_id, sale_item_id, qty, amount) VALUES (?,?,?,?)",
                          (rid, it["id"], qty, a))
                c.execute("UPDATE sale_items SET refunded_qty=refunded_qty+? WHERE id=?", (qty, it["id"]))
                if restock and it["product_id"]:
                    c.execute("UPDATE products SET stock_qty=stock_qty+?, updated_at=? WHERE id=? AND track_stock=1",
                              (qty, now, it["product_id"]))
            left = c.execute("SELECT SUM(qty-refunded_qty) FROM sale_items WHERE sale_id=?", (sid,)).fetchone()[0]
            status = "refunded" if not left else "partially_refunded"
            c.execute("UPDATE sales SET status=?, updated_at=? WHERE id=?", (status, now, sid))
        audit(self.db, user, "refund_processed", "sale", sid, {"refund_no": rno, "amount": amount, "reason": reason})
        if sale["customer_id"] and self.vip:
            self.vip.recalculate(sale["customer_id"], reason=f"refund {rno}")
        return rid

    def void(self, sid: int, reason: str):
        user = self.auth.require("sales.void")
        if not reason.strip():
            raise ValidationError("Enter the reason for voiding the sale.")
        sale = self.db.one("SELECT * FROM sales WHERE id=?", (sid,))
        if sale is None:
            raise NotFound("Sale not found.")
        if sale["status"] == "voided":
            raise ValidationError("This sale is already voided.")
        if self.db.scalar("SELECT COUNT(*) FROM refunds WHERE sale_id=?", (sid,)):
            raise ValidationError("This sale has refunds - refund the remaining items instead of voiding.")
        if self.settings.get("void_same_day_only") and \
                dt.date.fromtimestamp(sale["sold_at"]) != dt.date.today() and not self.auth.can("settings.manage"):
            raise PermissionDenied("Only an Admin can void a sale from an earlier day.")
        now = time.time()
        with self.db.tx() as c:
            c.execute("UPDATE sales SET status='voided', void_reason=?, voided_by=?, voided_at=?, updated_at=? WHERE id=?",
                      (reason.strip(), user.id or None, now, now, sid))
            for it in c.execute("SELECT product_id, qty FROM sale_items WHERE sale_id=?", (sid,)).fetchall():
                if it["product_id"]:
                    c.execute("UPDATE products SET stock_qty=stock_qty+?, updated_at=? WHERE id=? AND track_stock=1",
                              (it["qty"], now, it["product_id"]))
        audit(self.db, user, "sale_voided", "sale", sid, {"receipt": sale["receipt_no"], "reason": reason})
        if sale["customer_id"] and self.vip:
            self.vip.recalculate(sale["customer_id"], reason=f"void {sale['receipt_no']}")

    def link_customer(self, sid: int, customer_id: int, method: str):
        """Attach a sale made without a customer, using verified identification only."""
        user = self.auth.require("sales.refund")
        if method not in ("loyalty_id", "phone", "qr", "selected"):
            raise ValidationError("Link with a loyalty ID, phone number, QR code or by selecting the customer.")
        sale = self.db.one("SELECT customer_id, receipt_no, status FROM sales WHERE id=?", (sid,))
        if sale is None:
            raise NotFound("Sale not found.")
        if sale["customer_id"]:
            raise ValidationError("This sale already belongs to a customer.")
        self.db.execute("UPDATE sales SET customer_id=?, link_method=?, updated_at=? WHERE id=?",
                        (customer_id, method, time.time(), sid))
        audit(self.db, user, "sale_linked", "sale", sid, {"customer_id": customer_id, "method": method})
        if self.vip:
            self.vip.recalculate(customer_id, reason=f"linked {sale['receipt_no']}")


def _unit_share(line_total: int, qty: int, units: int) -> int:
    """Amount for the first `units` of a line - integer, exact for the whole line."""
    return (line_total * units * 2 + qty) // (2 * qty)        # round half-up of line_total*units/qty

"""Product catalogue and basic stock."""
from __future__ import annotations

import time

from app.models import Product
from app.security.audit import audit
from app.services.errors import NotFound, ValidationError


def _row(r) -> Product:
    return Product(r["id"], r["sku"], r["name"], r["category"], r["unit_price"], r["tax_rate_bp"], r["stock_qty"],
                   bool(r["track_stock"]), bool(r["active"]), bool(r["is_demo"]))


class ProductService:
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth

    def get(self, pid: int) -> Product:
        r = self.db.one("SELECT * FROM products WHERE id=?", (pid,))
        if r is None:
            raise NotFound("Product not found.")
        return _row(r)

    def by_sku(self, sku: str) -> Product | None:
        r = self.db.one("SELECT * FROM products WHERE sku=?", ((sku or "").strip(),))
        return _row(r) if r else None

    def search(self, text: str = "", category: str = "", active_only: bool = True, limit: int = 500) -> list[Product]:
        where, args = [], []
        if active_only:
            where.append("active=1")
        if text:
            where.append("(name LIKE ? OR sku LIKE ?)"); args += [f"%{text.strip()}%"] * 2
        if category:
            where.append("category=?"); args.append(category)
        sql = "SELECT * FROM products" + (" WHERE " + " AND ".join(where) if where else "") + \
              " ORDER BY name COLLATE NOCASE LIMIT ?"
        return [_row(r) for r in self.db.q(sql, (*args, limit))]

    def categories(self) -> list[str]:
        return [r[0] for r in self.db.q("SELECT DISTINCT category FROM products ORDER BY category COLLATE NOCASE")]

    def save(self, sku: str, name: str, category: str, unit_price: int, tax_rate_bp: int | None = None,
             stock_qty: int = 0, track_stock: bool = True, active: bool = True, pid: int | None = None,
             is_demo: bool = False) -> int:
        user = self.auth.require("products.manage")
        sku, name, category = (sku or "").strip(), " ".join((name or "").split()), (category or "General").strip() or "General"
        if not sku or len(sku) > 40:
            raise ValidationError("SKU is required (max 40 characters).")
        if len(name) < 2:
            raise ValidationError("Enter the product name.")
        if not isinstance(unit_price, int) or unit_price < 0:
            raise ValidationError("Price must be zero or more.")
        if tax_rate_bp is not None and not 0 <= tax_rate_bp <= 10000:
            raise ValidationError("Tax rate must be between 0% and 100%.")
        other = self.by_sku(sku)
        if other and other.id != pid:
            raise ValidationError(f"SKU {sku} is already used by {other.name}.")
        now = time.time()
        if pid:
            self.db.execute("UPDATE products SET sku=?, name=?, category=?, unit_price=?, tax_rate_bp=?, stock_qty=?, "
                            "track_stock=?, active=?, updated_at=? WHERE id=?",
                            (sku, name, category, unit_price, tax_rate_bp, int(stock_qty), int(track_stock), int(active),
                             now, pid))
            audit(self.db, user, "product_updated", "product", pid, {"sku": sku, "price": unit_price})
            return pid
        pid = self.db.execute("INSERT INTO products(sku, name, category, unit_price, tax_rate_bp, stock_qty, track_stock, "
                              "active, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (sku, name, category, unit_price, tax_rate_bp, int(stock_qty), int(track_stock),
                               int(active), int(is_demo), now, now))
        audit(self.db, user, "product_created", "product", pid, {"sku": sku})
        return pid

    def adjust_stock(self, pid: int, delta: int, reason: str):
        user = self.auth.require("products.manage")
        if not reason.strip():
            raise ValidationError("Give a reason for the stock adjustment.")
        p = self.get(pid)
        self.db.execute("UPDATE products SET stock_qty=stock_qty+?, updated_at=? WHERE id=?", (int(delta), time.time(), pid))
        audit(self.db, user, "stock_adjusted", "product", pid, {"sku": p.sku, "delta": delta, "reason": reason})

    def set_active(self, pid: int, active: bool):
        user = self.auth.require("products.manage")
        self.db.execute("UPDATE products SET active=?, updated_at=? WHERE id=?", (int(active), time.time(), pid))
        audit(self.db, user, "product_activated" if active else "product_deactivated", "product", pid)

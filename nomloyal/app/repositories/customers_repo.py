from __future__ import annotations

from app.models import Customer

COLS = ("id, loyalty_id, full_name, COALESCE(phone,'') phone, email, notes, tags, status, vip_tier, vip_reason, "
        "vip_override_tier, vip_override_reason, is_demo, created_at, updated_at")


def row_to_customer(r) -> Customer:
    return Customer(r["id"], r["loyalty_id"], r["full_name"], r["phone"], r["email"], r["notes"], r["tags"], r["status"],
                    r["vip_tier"], r["vip_reason"], r["vip_override_tier"], r["vip_override_reason"], bool(r["is_demo"]),
                    r["created_at"], r["updated_at"])


class CustomersRepo:
    def __init__(self, db):
        self.db = db

    def get(self, cid: int) -> Customer | None:
        r = self.db.one(f"SELECT {COLS} FROM customers WHERE id=?", (cid,))
        return row_to_customer(r) if r else None

    def by_loyalty_id(self, loyalty_id: str) -> Customer | None:
        r = self.db.one(f"SELECT {COLS} FROM customers WHERE loyalty_id=? COLLATE NOCASE", (loyalty_id.strip(),))
        return row_to_customer(r) if r else None

    def by_phone(self, phone: str) -> Customer | None:
        if not phone:
            return None
        r = self.db.one(f"SELECT {COLS} FROM customers WHERE phone=?", (phone,))
        return row_to_customer(r) if r else None

    def search(self, text: str = "", status: str | None = "active", tier: str | None = None, limit: int = 500,
               offset: int = 0, order: str = "name") -> list[Customer]:
        where, args = [], []
        if status:
            where.append("status=?"); args.append(status)
        if text:
            t = f"%{text.strip()}%"
            digits = "".join(ch for ch in text if ch.isdigit())
            cond = "(full_name LIKE ? OR loyalty_id LIKE ? OR email LIKE ? OR tags LIKE ?"
            args += [t, t, t, t]
            if digits:
                cond += " OR phone LIKE ?"; args.append(f"%{digits}%")
            where.append(cond + ")")
        if tier == "__none__":
            where.append("COALESCE(vip_override_tier, vip_tier) IS NULL")
        elif tier:
            where.append("COALESCE(vip_override_tier, vip_tier)=?"); args.append(tier)
        orders = {"name": "full_name COLLATE NOCASE", "newest": "created_at DESC", "updated": "updated_at DESC"}
        sql = f"SELECT {COLS} FROM customers" + (" WHERE " + " AND ".join(where) if where else "") + \
              f" ORDER BY {orders.get(order, orders['name'])} LIMIT ? OFFSET ?"
        return [row_to_customer(r) for r in self.db.q(sql, (*args, limit, offset))]

    def count(self, text: str = "", status: str | None = "active", tier: str | None = None) -> int:
        return len(self.search(text, status, tier, limit=1_000_000))

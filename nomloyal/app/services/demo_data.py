"""Sample data for trying the app. Every demo record is flagged is_demo=1, shown as DEMO and removable."""
from __future__ import annotations

import random
import time

from app.models import CartLine
from app.money import to_minor
from app.security.audit import audit
from app.services.errors import ValidationError

PRODUCTS = [
    ("SH-101", "Cotton formal shirt", "Shirts", "3,450"), ("SH-102", "Linen casual shirt", "Shirts", "4,200"),
    ("SA-201", "Banarasi silk saree", "Sarees", "18,500"), ("SA-202", "Bridal embroidered saree", "Sarees", "52,000"),
    ("SA-203", "Chiffon printed saree", "Sarees", "7,800"), ("SO-301", "Leather loafers", "Shoes", "9,900"),
    ("SO-302", "Ladies khussa", "Shoes", "3,200"), ("JW-401", "Gold-plated jhumka", "Jewellery", "6,500"),
    ("JW-402", "Kundan necklace set", "Jewellery", "24,000"), ("CO-501", "Lipstick (matte)", "Cosmetics", "1,850"),
    ("CO-502", "Skin care gift box", "Cosmetics", "5,400"), ("AC-601", "Pashmina shawl", "Accessories", "11,500"),
]
NAMES = ["Ayesha Khan", "Bilal Ahmed", "Sana Malik", "Usman Tariq", "Hira Javed", "Fatima Noor", "Zainab Ali",
         "Hamza Qureshi", "Mariam Siddiqui", "Imran Shah", "Nadia Hussain", "Omar Farooq", "Rabia Aslam",
         "Saad Iqbal", "Mehwish Raza", "Kamran Baig", "Iqra Saleem", "Ahmed Raza", "Maha Rehman", "Tariq Mehmood",
         "Amna Butt", "Faisal Khan", "Sadia Anwar", "Noman Akhtar"]


def has_demo(db) -> bool:
    return bool(db.scalar("SELECT 1 FROM customers WHERE is_demo=1 UNION SELECT 1 FROM sales WHERE is_demo=1 LIMIT 1"))


def load_demo(ctx, seed: int = 7) -> dict:
    ctx.auth.require("demo.manage")
    if has_demo(ctx.db):
        raise ValidationError("Demo data is already loaded.")
    rng = random.Random(seed)
    pids = []
    for sku, name, cat, price in PRODUCTS:
        if ctx.products.by_sku(sku):
            continue
        pids.append(ctx.products.save(sku, name, cat, to_minor(price), None, rng.randint(120, 200), True, True,
                                      is_demo=True))
    everyday = [p.id for p in ctx.products.search() if p.sku not in ("SA-202", "JW-402") and p.unit_price <= 1_200_000]
    custs = []
    for i, n in enumerate(NAMES):
        custs.append(ctx.customers.create(n, f"0300{5550100 + i:07d}", f"{n.split()[0].lower()}@example.com",
                                          tags=rng.choice(["", "bridal", "family", "office", ""]),
                                          data_consent=True, marketing_consent=rng.random() < 0.5, is_demo=True))
    now = time.time()
    by_sku = {p.sku: p.id for p in ctx.products.search(active_only=False)}
    n_sales = 0
    # the scenario from the brief: an expensive saree makes Ayesha a VIP
    ctx.sales.checkout([CartLine(by_sku["SH-101"], 2), CartLine(by_sku["SA-202"], 1)], "Card", custs[0].id,
                       "loyalty_id", sold_at=now - 92 * 86400, is_demo=True)
    n_sales += 1
    for _ in range(110):
        when = now - rng.uniform(0.02, 150) * 86400
        lines = [CartLine(rng.choice(everyday), rng.choice([1, 1, 1, 1, 2])) for _ in range(rng.choice([1, 1, 1, 2]))]
        merged: dict[int, int] = {}
        for l in lines:
            merged[l.product_id] = merged.get(l.product_id, 0) + l.qty
        cart = [CartLine(pid, q) for pid, q in merged.items()]
        if rng.random() < 0.72:
            c = custs[min(int(rng.expovariate(0.12)), len(custs) - 1)]
            cid, method = c.id, rng.choice(["loyalty_id", "phone", "qr", "selected"])
        else:
            cid, method = None, "none"
        ctx.sales.checkout(cart, rng.choice(["Cash", "Card", "Mobile wallet"]), cid, method,
                           invoice_discount=0, sold_at=when, is_demo=True)
        n_sales += 1
    # two refunds
    for r in ctx.db.q("SELECT id FROM sales WHERE is_demo=1 AND customer_id IS NOT NULL ORDER BY sold_at DESC LIMIT 2"):
        item = ctx.db.one("SELECT id FROM sale_items WHERE sale_id=? LIMIT 1", (r["id"],))
        ctx.sales.refund(r["id"], {item["id"]: 1}, "Demo: size exchange", "Cash", True)
    # a returning visit -> alert
    ctx.customers.check_in(custs[0].id, "loyalty_id", "Demo check-in")
    ctx.settings.set("demo_data_loaded", True)
    audit(ctx.db, ctx.auth.user, "demo_loaded", "demo", "", {"customers": len(custs), "sales": n_sales})
    return {"products": len(PRODUCTS), "customers": len(custs), "sales": n_sales}


def remove_demo(ctx) -> dict:
    """Remove ONLY demo records. Real customers, products and sales are untouched."""
    ctx.auth.require("demo.manage")
    db = ctx.db
    out = {}
    with db.tx() as c:
        demo_sales = "SELECT id FROM sales WHERE is_demo=1"
        c.execute(f"DELETE FROM refund_items WHERE refund_id IN (SELECT id FROM refunds WHERE sale_id IN ({demo_sales}))")
        c.execute(f"DELETE FROM refunds WHERE sale_id IN ({demo_sales})")
        c.execute(f"DELETE FROM sale_items WHERE sale_id IN ({demo_sales})")
        out["sales"] = c.execute("DELETE FROM sales WHERE is_demo=1").rowcount
        demo_c = "SELECT id FROM customers WHERE is_demo=1"
        c.execute(f"UPDATE sales SET customer_id=NULL, link_method='none' WHERE customer_id IN ({demo_c})")
        c.execute(f"DELETE FROM customer_visits WHERE customer_id IN ({demo_c}) OR is_demo=1")
        c.execute(f"DELETE FROM alerts WHERE customer_id IN ({demo_c}) OR is_simulated=1")
        c.execute(f"DELETE FROM consent_records WHERE customer_id IN ({demo_c})")
        out["customers"] = c.execute("DELETE FROM customers WHERE is_demo=1").rowcount
        # demo products still used by a real sale are kept (and become normal products)
        c.execute("UPDATE products SET is_demo=0 WHERE is_demo=1 AND id IN (SELECT product_id FROM sale_items "
                  "WHERE product_id IS NOT NULL)")
        out["products"] = c.execute("DELETE FROM products WHERE is_demo=1").rowcount
    ctx.settings.set("demo_data_loaded", False)
    audit(db, ctx.auth.user, "demo_removed", "demo", "", out)
    return out

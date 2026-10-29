import pytest

from app.models import CartLine
from app.money import fmt, to_minor
from app.services.errors import ValidationError
from app.services.sales_service import price_lines, split_proportional


def test_money_parsing_and_format():
    assert to_minor("1,250.50") == 125050
    assert to_minor("0.005") == 1          # half-up
    assert fmt(5_000_000) == "Rs 50,000"
    with pytest.raises(ValueError):
        to_minor("-5")


def test_split_is_exact():
    parts = split_proportional(1000, [333, 333, 334])
    assert sum(parts) == 1000 and parts == [333, 333, 334]
    assert sum(split_proportional(7, [1, 1, 1])) == 7


def test_multi_item_sale_totals(ctx, shop):
    ctx.settings.set("tax_rate_bp", 0)
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 2, to_minor("500")), CartLine(shop["perfume"], 3)], "Cash",
                             invoice_discount=to_minor("450"))
    s = ctx.sales.get(sid)
    assert s["subtotal"] == to_minor("8000")            # 2 x 2,500 + 3 x 1,000
    assert s["discount_total"] == to_minor("950")       # 500 line + 450 invoice
    # invoice discount shared 4,500 : 3,000 -> 270 / 180; perfume taxable 2,820 x 17% = 479.40
    perfume = next(i for i in s["items"] if i["sku"] == "PF-1")
    assert perfume["invoice_discount_share"] == to_minor("180")
    assert perfume["line_tax"] == to_minor("479.40")
    assert s["tax_total"] == to_minor("479.40")
    assert s["total"] == to_minor("8000") - to_minor("950") + to_minor("479.40")
    assert s["total"] == sum(i["line_total"] for i in s["items"])


def test_prices_come_from_catalogue_not_ui(ctx, shop):
    q = ctx.sales.quote([CartLine(shop["saree"], 1)])
    assert q.total == to_minor("50000")


def test_validation(ctx, shop):
    with pytest.raises(ValidationError):
        ctx.sales.checkout([], "Cash")
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 0)], "Cash")
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 1, to_minor("3000"))], "Cash")     # discount > line
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Bitcoin")
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["saree"], 11)], "Cash")                     # stock is 10


def test_receipt_numbers_unique_and_stock(ctx, shop):
    a = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    b = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    ra, rb = ctx.sales.get(a)["receipt_no"], ctx.sales.get(b)["receipt_no"]
    assert ra != rb and rb.endswith("0002")
    assert ctx.products.get(shop["shirt"]).stock_qty == 48
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        ctx.db.execute("INSERT INTO sales(receipt_no, sold_at, subtotal, discount_total, tax_total, total, payment_method, "
                       "created_at, updated_at) VALUES (?,0,0,0,0,0,'Cash',0,0)", (ra,))


def test_customer_link_requires_evidence(ctx, shop):
    c = ctx.customers.create("Ayesha Khan", "0300-1234567", data_consent=True)
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "none")
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", None, "phone")
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "phone")
    s = ctx.sales.get(sid)
    assert s["customer_id"] == c.id and s["link_method"] == "phone"
    assert ctx.reports.customer_stats(c.id)["net"] == to_minor("2500")


def test_failed_sale_writes_nothing(ctx, shop):
    before = ctx.db.scalar("SELECT COUNT(*) FROM sales")
    with pytest.raises(ValidationError):
        ctx.sales.checkout([CartLine(shop["shirt"], 1), CartLine(shop["saree"], 99)], "Cash")
    assert ctx.db.scalar("SELECT COUNT(*) FROM sales") == before
    assert ctx.products.get(shop["shirt"]).stock_qty == 50


def test_lifetime_net_spending(ctx, shop):
    c = ctx.customers.create("Bilal Ahmed", "03001112223", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash", c.id, "loyalty_id")
    sid = ctx.sales.checkout([CartLine(shop["saree"], 1)], "Card", c.id, "qr")
    voided = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "selected")
    ctx.sales.void(voided, "wrong item")
    item = ctx.sales.get(sid)["items"][0]
    ctx.sales.refund(sid, {item["id"]: 1}, "returned", "Card")
    st = ctx.reports.customer_stats(c.id)
    assert st["net"] == to_minor("5000")         # 5,000 + 50,000 - 50,000 refund; voided ignored
    assert st["transactions"] == 2
    assert st["favorite_categories"][0] in ("Shirts", "Sarees")


def test_price_lines_rounding():
    q = price_lines([{"sku": "A", "name": "A", "category": "X", "qty": 3, "unit_price": 333, "line_discount": 0,
                      "tax_rate_bp": 1700, "product_id": 1}], 0, 0)
    assert q.tax_total == 170 and q.total == 999 + 170

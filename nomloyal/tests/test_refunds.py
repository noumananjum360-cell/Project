import pytest

from app.models import CartLine
from app.money import to_minor
from app.services.errors import ValidationError


def test_partial_then_full_refund_equals_amount_paid(ctx, shop):
    sid = ctx.sales.checkout([CartLine(shop["perfume"], 3)], "Cash", invoice_discount=to_minor("100"))
    s = ctx.sales.get(sid)
    item = s["items"][0]
    ctx.sales.refund(sid, {item["id"]: 1}, "damaged")
    assert ctx.sales.get(sid)["status"] == "partially_refunded"
    ctx.sales.refund(sid, {item["id"]: 2}, "changed mind")
    s2 = ctx.sales.get(sid)
    assert s2["status"] == "refunded"
    assert s2["refunded_total"] == s["total"]          # exact to the paisa
    assert ctx.products.get(shop["perfume"]).stock_qty == 20


def test_cannot_refund_more_than_sold(ctx, shop):
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash")
    item = ctx.sales.get(sid)["items"][0]
    with pytest.raises(ValidationError):
        ctx.sales.refund(sid, {item["id"]: 3}, "too many")
    ctx.sales.refund(sid, {item["id"]: 2}, "ok")
    with pytest.raises(ValidationError):
        ctx.sales.refund(sid, {item["id"]: 1}, "again")


def test_refund_needs_reason_and_not_voided(ctx, shop):
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    item = ctx.sales.get(sid)["items"][0]
    with pytest.raises(ValidationError):
        ctx.sales.refund(sid, {item["id"]: 1}, " ")
    ctx.sales.void(sid, "test")
    with pytest.raises(ValidationError):
        ctx.sales.refund(sid, {item["id"]: 1}, "after void")


def test_void_rules(ctx, shop):
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash")
    assert ctx.products.get(shop["shirt"]).stock_qty == 48
    ctx.sales.void(sid, "keyed twice")
    assert ctx.sales.get(sid)["status"] == "voided"
    assert ctx.products.get(shop["shirt"]).stock_qty == 50
    with pytest.raises(ValidationError):
        ctx.sales.void(sid, "again")
    sid2 = ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash")
    ctx.sales.refund(sid2, {ctx.sales.get(sid2)["items"][0]["id"]: 1}, "r")
    with pytest.raises(ValidationError):
        ctx.sales.void(sid2, "has refund")


def test_voided_sales_excluded_from_reports(ctx, shop):
    import datetime as dt
    a = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    ctx.sales.void(a, "x")
    s = ctx.reports.summary(dt.date.today(), dt.date.today())
    assert s["transactions"] == 1 and s["net"] == to_minor("2500") and s["voided"] == 1


def test_sales_cannot_be_deleted(ctx, shop):
    import sqlite3
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    with pytest.raises(sqlite3.DatabaseError):
        ctx.db.execute("DELETE FROM sales WHERE id=?", (sid,))

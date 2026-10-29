import time

import pytest

from app.models import CartLine
from app.money import to_minor
from app.services.errors import ValidationError


def test_single_purchase_rule_a(ctx, shop):
    c = ctx.customers.create("Ayesha Khan", "0300-1234567", data_consent=True)
    ctx.sales.checkout([CartLine(shop["saree"], 1), CartLine(shop["shirt"], 2)], "Card", c.id, "loyalty_id")
    e = ctx.vip.evaluate(c.id)
    assert e.tier == "VIP"
    assert any("Single purchase" in r for r in e.reasons)
    assert e.qualifying_sales
    assert ctx.customers.get(c.id).tier == "VIP"


def test_rolling_rule_b_and_window(ctx, shop):
    c = ctx.customers.create("Sana Malik", "03002223334", data_consent=True)
    ctx.products.adjust_stock(shop["shirt"], 100, "test stock")
    old = time.time() - 400 * 86400
    for _ in range(15):
        ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash", c.id, "phone", sold_at=old)   # 75,000, too old
    assert ctx.vip.evaluate(c.id).tier is None
    for _ in range(10):
        ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash", c.id, "phone")               # 50,000 in window
    assert ctx.vip.evaluate(c.id).tier == "Silver"
    for _ in range(10):
        ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash", c.id, "phone")               # 100,000
    e = ctx.vip.evaluate(c.id)
    assert e.tier == "VIP" and any("Net spending" in r for r in e.reasons)


def test_vip_drops_after_refund(ctx, shop):
    c = ctx.customers.create("Hira Javed", "03003334445", data_consent=True)
    sid = ctx.sales.checkout([CartLine(shop["saree"], 1)], "Card", c.id, "qr")
    assert ctx.customers.get(c.id).tier == "VIP"
    ctx.sales.refund(sid, {ctx.sales.get(sid)["items"][0]["id"]: 1}, "returned")
    assert ctx.customers.get(c.id).tier is None
    assert ctx.customers.get(c.id).vip_reason.startswith("No tier")


def test_void_removes_vip(ctx, shop):
    c = ctx.customers.create("Omar Farooq", "03004445556", data_consent=True)
    sid = ctx.sales.checkout([CartLine(shop["saree"], 1)], "Card", c.id, "qr")
    ctx.sales.void(sid, "card declined")
    assert ctx.customers.get(c.id).tier is None


def test_rule_change_recalculates_everyone(ctx, shop):
    c = ctx.customers.create("Zainab Ali", "03005556667", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 4)], "Cash", c.id, "phone")            # 10,000
    assert ctx.customers.get(c.id).tier is None
    tid = next(t.id for t in ctx.vip.tiers() if t.name == "Bronze")
    ctx.vip.save_tier("Bronze", 1, None, to_minor("10000"), 12, "#A86B3C", True, tid)
    assert ctx.customers.get(c.id).tier == "Bronze"


def test_custom_tier_and_validation(ctx, shop):
    with pytest.raises(ValidationError):
        ctx.vip.save_tier("Platinum", 5, None, None)
    ctx.vip.save_tier("Platinum", 5, to_minor("200000"), None)
    assert [t.name for t in ctx.vip.tiers()][-1] == "Platinum"


def test_manual_override_is_audited(ctx, shop):
    c = ctx.customers.create("Imran Shah", "03006667778", data_consent=True)
    with pytest.raises(ValidationError):
        ctx.vip.override(c.id, "Gold", "")
    ctx.vip.override(c.id, "Gold", "Owner's family")
    assert ctx.customers.get(c.id).tier == "Gold"
    assert ctx.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='vip_override_set'") == 1
    ctx.vip.override(c.id, None, "removed")
    assert ctx.customers.get(c.id).tier is None

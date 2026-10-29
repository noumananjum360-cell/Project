import pytest

from app.models import CartLine
from app.money import to_minor
from app.security.authentication import AuthError
from app.security.permissions import PermissionDenied
from tests.conftest import make_staff


def as_user(ctx, staff):
    ctx.auth.user = staff


def test_cashier_limits(ctx, shop):
    cashier = make_staff(ctx, "Cashier")
    c = ctx.customers.create("Ayesha Khan", "0300-1234567", data_consent=True)
    as_user(ctx, cashier)
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "phone")
    for fn in (lambda: ctx.sales.refund(sid, {1: 1}, "x"), lambda: ctx.sales.void(sid, "x"),
               lambda: ctx.vip.override(c.id, "Gold", "x"), lambda: ctx.backup.backup(),
               lambda: ctx.products.save("X-1", "Thing", "G", 100), lambda: ctx.privacy.delete_customer(c.id, "x"),
               lambda: ctx.privacy.export_customer(c.id, "/tmp/x.zip"),
               lambda: ctx.customers.update(c.id, "A", "", "", "", ""),
               lambda: ctx.auth.create("x", "Passw0rd!", "Admin")):
        with pytest.raises(PermissionDenied):
            fn()
    with pytest.raises(PermissionDenied):         # discount above the cashier limit (10%)
        ctx.sales.checkout([CartLine(shop["shirt"], 1, to_minor("500"))], "Cash")


def test_cashier_sees_only_own_sales(ctx, shop):
    a = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    cashier = make_staff(ctx, "Cashier")
    as_user(ctx, cashier)
    mine = ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    assert [s["id"] for s in ctx.sales.search()] == [mine]
    with pytest.raises(PermissionDenied):
        ctx.sales.get(a)


def test_manager_rights(ctx, shop):
    mgr = make_staff(ctx, "Manager")
    as_user(ctx, mgr)
    sid = ctx.sales.checkout([CartLine(shop["shirt"], 2)], "Cash")
    ctx.sales.refund(sid, {ctx.sales.get(sid)["items"][0]["id"]: 1}, "ok")
    with pytest.raises(PermissionDenied):
        ctx.vip.save_tier("X", 9, None, 100)
    with pytest.raises(PermissionDenied):
        ctx.backup.backup()
    ctx.settings.set("manager_can_edit_vip_rules", True)
    ctx.vip.save_tier("X", 9, None, 100)


def test_login_lockout_and_no_default_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOYAL_HOME", str(tmp_path))
    from app.context import AppContext
    c = AppContext(tmp_path / "x.db")
    assert c.auth.needs_first_run() and c.db.scalar("SELECT COUNT(*) FROM staff_users") == 0
    with pytest.raises(AuthError):
        c.auth.create("a", "short", "Admin", first_run=True)
    c.auth.create("owner", "Owner1234", "Admin", first_run=True)
    with pytest.raises(AuthError):
        c.auth.create("second", "Owner1234", "Admin", first_run=True)
    for _ in range(5):
        with pytest.raises(AuthError):
            c.auth.login("owner", "wrong")
    with pytest.raises(AuthError, match="Too many"):
        c.auth.login("owner", "Owner1234")
    stored = c.db.scalar("SELECT password_hash FROM staff_users")
    assert stored.startswith("scrypt$") and "Owner1234" not in stored
    assert "Owner1234" not in " ".join(str(r["details"]) for r in c.db.q("SELECT details FROM audit_log"))
    c.close()


def test_last_admin_protected(ctx):
    with pytest.raises(AuthError):
        ctx.auth.update(ctx.auth.user.id, active=False)
    with pytest.raises(AuthError):
        ctx.auth.update(ctx.auth.user.id, role="Cashier")


def test_audit_log_append_only(ctx):
    import sqlite3
    with pytest.raises(sqlite3.DatabaseError):
        ctx.db.execute("DELETE FROM audit_log")
    with pytest.raises(sqlite3.DatabaseError):
        ctx.db.execute("UPDATE audit_log SET action='x'")

import pytest

from app.models import CartLine
from app.services.customer_service import luhn_digit, normalize_phone, valid_loyalty_id
from app.services.errors import NotFound, ValidationError


def test_create_edit_archive(ctx):
    c = ctx.customers.create("  Ayesha   Khan ", "+92 300 1234567", "ayesha@example.com", tags="bridal; silk",
                             data_consent=True)
    assert c.full_name == "Ayesha Khan" and c.phone == "03001234567" and c.tags == "bridal, silk"
    assert valid_loyalty_id(c.loyalty_id)
    c2 = ctx.customers.update(c.id, "Ayesha K.", "0300-1234567", "a@example.com", "VIP bride", "bridal")
    assert c2.full_name == "Ayesha K." and c2.notes == "VIP bride"
    ctx.customers.set_archived(c.id, True)
    assert not ctx.customers.search("Ayesha")
    assert ctx.customers.search("Ayesha", status="archived")


def test_validation_and_duplicates(ctx):
    with pytest.raises(ValidationError):
        ctx.customers.create("A", data_consent=True)
    with pytest.raises(ValidationError):
        ctx.customers.create("Bilal", "123", data_consent=True)
    with pytest.raises(ValidationError):
        ctx.customers.create("Bilal", email="not-an-email", data_consent=True)
    with pytest.raises(ValidationError, match="consent"):
        ctx.customers.create("Bilal Ahmed", "03001112223")
    ctx.customers.create("Bilal Ahmed", "03001112223", data_consent=True)
    with pytest.raises(ValidationError, match="already exists"):
        ctx.customers.create("Other", "0300-111-2223", data_consent=True)


def test_lookup_methods(ctx):
    c = ctx.customers.create("Sana Malik", "0321-5550001", data_consent=True)
    assert ctx.customers.lookup(c.loyalty_id)[1] == "loyalty_id"
    assert ctx.customers.lookup(c.loyalty_id.replace("-", "").lower())[0].id == c.id
    assert ctx.customers.lookup("+92 321 5550001") == (c, "phone") or ctx.customers.lookup("+92 321 5550001")[1] == "phone"
    assert ctx.customers.lookup(ctx.customers.qr_payload(c))[1] == "qr"
    with pytest.raises(NotFound):
        ctx.customers.lookup("0321-5550002")
    with pytest.raises(NotFound):
        ctx.customers.lookup("NL-9999990")


def test_luhn_and_phone():
    assert luhn_digit("000001") == "8"
    assert normalize_phone("923001234567") == "03001234567"
    assert normalize_phone("") == ""


def test_check_in_raises_one_alert(ctx, shop):
    import time
    c = ctx.customers.create("Hira Javed", "03003334445", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "phone", sold_at=time.time() - 90 * 86400)
    a1 = ctx.customers.check_in(c.id, "loyalty_id")
    a2 = ctx.customers.check_in(c.id, "phone")           # duplicate within 30 minutes
    assert a1 and a2 is None
    alert = ctx.alerts.list()[0]
    assert alert["customer"] == "Hira Javed" and not alert["is_simulated"]
    ctx.alerts.handle(a1, "acknowledged")
    assert ctx.alerts.open_count() == 0


def test_os_notification_has_no_personal_data(ctx, shop):
    import time
    sent = []
    ctx.alerts.notifier = lambda t, m: sent.append((t, m))
    c = ctx.customers.create("Fatima Noor", "03007778889", data_consent=True)
    ctx.sales.checkout([CartLine(shop["saree"], 1)], "Card", c.id, "qr", sold_at=time.time() - 10 * 86400)
    ctx.customers.check_in(c.id, "qr")
    assert sent and "Fatima" not in sent[0][1] and "50" not in sent[0][1]


def test_simulated_alert_is_labelled(ctx):
    c = ctx.customers.create("Zainab Ali", "03005556667", data_consent=True)
    import time
    ctx.db.execute("INSERT INTO customer_visits(customer_id, visited_at, method, created_at) VALUES (?,?,'x',0)",
                   (c.id, time.time() - 10 * 86400))
    aid = ctx.customers.check_in(c.id, "demo", simulated=True)
    a = ctx.alerts.list()[0]
    assert a["id"] == aid and a["is_simulated"] and "SIMULATED" in a["title"]


def test_persistence_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOYAL_HOME", str(tmp_path))
    from app.context import AppContext
    path = tmp_path / "p.db"
    c = AppContext(path)
    c.auth.create("owner", "Owner1234", "Admin", first_run=True)
    c.auth.login("owner", "Owner1234")
    pid = c.products.save("SH-1", "Shirt", "Shirts", 250000, None, 5)
    cust = c.customers.create("Persist Me", "03009990001", data_consent=True)
    c.sales.checkout([CartLine(pid, 1)], "Cash", cust.id, "phone")
    c.close()
    c2 = AppContext(path)
    c2.auth.login("owner", "Owner1234")
    assert c2.customers.lookup("03009990001")[0].full_name == "Persist Me"
    assert c2.reports.customer_stats(cust.id)["net"] == 250000
    c2.close()

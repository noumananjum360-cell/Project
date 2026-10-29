import zipfile

from app.models import CartLine


def test_consent_history_and_withdrawal(ctx):
    c = ctx.customers.create("Rabia Aslam", "03001231231", data_consent=True, marketing_consent=True)
    assert ctx.privacy.consent_status(c.id) == {"data_processing": True, "marketing": True, "biometric": False}
    ctx.privacy.record_consent(c.id, "marketing", False, notes="customer asked")
    assert ctx.privacy.consent_status(c.id)["marketing"] is False
    assert len(ctx.privacy.consent_history(c.id)) == 3


def test_biometric_consent_needs_a_provider(ctx):
    import pytest
    from app.services.errors import ValidationError
    c = ctx.customers.create("Saad Iqbal", "03001231232", data_consent=True)
    with pytest.raises(ValidationError):
        ctx.privacy.record_consent(c.id, "biometric", True)


def test_export_customer_data(ctx, shop, tmp_path):
    c = ctx.customers.create("Export Person", "03001231233", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", c.id, "phone")
    p = ctx.privacy.export_customer(c.id, tmp_path / "x.zip")
    with zipfile.ZipFile(p) as z:
        assert {"customer_data.json", "purchases.csv"} <= set(z.namelist())
        assert "Export Person" in z.read("customer_data.json").decode()


def test_delete_without_sales_and_anonymize_with_sales(ctx, shop):
    a = ctx.customers.create("No Sales", "03001231234", data_consent=True)
    b = ctx.customers.create("Has Sales", "03001231235", data_consent=True)
    sid = ctx.sales.checkout([CartLine(shop["saree"], 1)], "Card", b.id, "phone")
    assert ctx.privacy.delete_customer(a.id, "customer request") == "deleted"
    assert ctx.customers.repo.get(a.id) is None
    assert ctx.privacy.delete_customer(b.id, "customer request") == "anonymized"
    gone = ctx.customers.repo.get(b.id)
    assert gone.full_name.startswith("Deleted customer") and gone.phone == "" and gone.tier is None
    assert ctx.sales.get(sid)["total"] == 5000000         # the store's accounts are intact


def test_retention(ctx, shop):
    import time
    c = ctx.customers.create("Old Visitor", "03001231236", data_consent=True)
    ctx.db.execute("INSERT INTO customer_visits(customer_id, visited_at, method, created_at) VALUES (?,?,?,?)",
                   (c.id, time.time() - 400 * 86400, "phone", 0))
    out = ctx.privacy.apply_retention()
    assert out["visits"] == 1 and out["customers"] == 0
    ctx.settings.set("retention_inactive_customer_months", 12)
    ctx.db.execute("UPDATE customers SET updated_at=? WHERE id=?", (time.time() - 400 * 86400, c.id))
    assert ctx.privacy.apply_retention()["customers"] == 1


def test_demo_data_load_and_remove_keeps_real_data(ctx, shop):
    from app.services.demo_data import has_demo, load_demo, remove_demo
    real = ctx.customers.create("Real Customer", "03001231299", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash", real.id, "phone")
    load_demo(ctx)
    assert has_demo(ctx.db)
    remove_demo(ctx)
    assert not has_demo(ctx.db)
    assert ctx.customers.get(real.id).full_name == "Real Customer"
    assert ctx.db.scalar("SELECT COUNT(*) FROM sales") == 1

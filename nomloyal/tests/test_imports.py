import csv

from app.models import CartLine
from app.money import to_minor
from app.services.import_service import TEMPLATES, write_template


def _csv(path, kind, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TEMPLATES[kind])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def test_templates_round_trip(ctx, tmp_path):
    for kind in TEMPLATES:
        p = write_template(kind, tmp_path / f"{kind}.csv")
        assert p.read_text(encoding="utf-8-sig").splitlines()[0].split(",") == TEMPLATES[kind]


def test_customer_import_validation_and_duplicates(ctx, tmp_path):
    ctx.customers.create("Existing", "03001234567", data_consent=True)
    p = _csv(tmp_path / "c.csv", "customers", [
        {"full_name": "Good One", "phone": "0300-7654321", "data_consent": "yes"},
        {"full_name": "Dup Phone", "phone": "0300-1234567", "data_consent": "yes"},
        {"full_name": "No Consent", "phone": "0300-1111111", "data_consent": "no"},
        {"full_name": "Bad Mail", "email": "nope", "data_consent": "yes"},
        {"full_name": "Twice", "phone": "0300-7654321", "data_consent": "yes"},
    ])
    pv = ctx.imports.preview("customers", p)
    assert [r.status for r in pv.rows] == ["ok", "duplicate", "error", "error", "duplicate"]
    assert ctx.imports.commit(pv) == 1
    assert ctx.customers.lookup("03007654321")[0].full_name == "Good One"
    job = ctx.imports.jobs()[0]
    assert job["rows_ok"] == 1 and job["rows_error"] == 2 and job["rows_duplicate"] == 2


def test_product_import(ctx, tmp_path):
    p = _csv(tmp_path / "p.csv", "products", [
        {"sku": "A-1", "name": "Shirt", "category": "Shirts", "unit_price": "2,500", "tax_rate_percent": "17",
         "stock_qty": "5", "track_stock": "yes"},
        {"sku": "A-2", "name": "Bad", "unit_price": "abc"},
    ])
    pv = ctx.imports.preview("products", p)
    assert [r.status for r in pv.rows] == ["ok", "error"]
    ctx.imports.commit(pv)
    pr = ctx.products.by_sku("A-1")
    assert pr.unit_price == 250000 and pr.tax_rate_bp == 1700


def test_sales_import_links_reconciles_and_skips_duplicates(ctx, shop, tmp_path):
    c = ctx.customers.create("Ayesha Khan", "03001234567", data_consent=True)
    rows = [
        {"receipt_no": "POS-1", "sold_at": "2026-01-05 12:00", "customer_phone": "0300-1234567", "sku": "SA-1", "qty": "1",
         "unit_price": "50000", "payment_method": "Card", "reported_total": "52500"},
        {"receipt_no": "POS-1", "sold_at": "2026-01-05 12:00", "customer_phone": "0300-1234567", "sku": "SH-1", "qty": "1",
         "unit_price": "2500", "payment_method": "Card", "reported_total": "52500"},
        {"receipt_no": "POS-2", "sold_at": "2026-01-06 10:00", "sku": "SH-1", "qty": "1", "unit_price": "2500",
         "payment_method": "Cash", "reported_total": "9999"},                      # does not reconcile
        {"receipt_no": "POS-3", "sold_at": "2026-01-06 11:00", "sku": "NOPE", "qty": "1", "unit_price": "1"},
        {"receipt_no": "POS-4", "sold_at": "2026-01-07 11:00", "customer_phone": "0399-0000000", "sku": "SH-1",
         "qty": "1", "unit_price": "2500", "payment_method": "Cash"},              # unknown phone -> no customer
    ]
    pv = ctx.imports.preview("sales", _csv(tmp_path / "s.csv", "sales", rows))
    st = {r.line: r.status for r in pv.rows}
    assert st[2] == "ok" and st[4] == "error" and st[5] == "error" and st[6] == "warning"
    assert ctx.imports.commit(pv) == 2
    s = ctx.sales.by_receipt("POS-1")
    assert s["customer_id"] == c.id and s["link_method"] == "pos_import" and s["total"] == to_minor("52500")
    assert ctx.sales.by_receipt("POS-4")["customer_id"] is None
    assert ctx.customers.get(c.id).tier == "VIP"
    assert ctx.products.get(shop["saree"]).stock_qty == 10        # historical import: stock unchanged
    pv2 = ctx.imports.preview("sales", _csv(tmp_path / "s2.csv", "sales", rows[:2]))
    assert pv2.rows[0].status == "duplicate"


def test_export_round_trip(ctx, shop, tmp_path):
    ctx.customers.create("Export Me", "03001112223", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    assert ctx.imports.export("customers", tmp_path / "c.csv") == 1
    assert ctx.imports.export("products", tmp_path / "p.csv") == 3
    assert ctx.imports.export("sales", tmp_path / "s.csv") == 1


def test_example_pos_adapter(ctx, shop, tmp_path):
    import json
    from app.integrations.pos_csv import CsvFolderConnector, ExampleJsonPOSAdapter
    f = tmp_path / "export.json"
    f.write_text(json.dumps({"receipts": [{"number": "X-1", "date": "2026-02-01 10:00", "payment": "Cash",
                                           "total": 2500, "lines": [{"sku": "SH-1", "qty": 1, "price": 2500}]}]}))
    a = ExampleJsonPOSAdapter(f)
    assert a.test_connection()[0]
    pv = ctx.imports.preview("sales", f, a.fetch_sales_rows())
    assert ctx.imports.commit(pv) == 1
    folder = tmp_path / "drop"
    folder.mkdir()
    _csv(folder / "day1.csv", "sales", [{"receipt_no": "F-1", "sold_at": "2026-02-02 10:00", "sku": "SH-1", "qty": "1",
                                         "unit_price": "2500", "payment_method": "Cash"}])
    con = CsvFolderConnector(folder)
    assert "1 CSV" in con.test_connection()[1]
    ctx.imports.commit(ctx.imports.preview("sales", "folder", con.fetch_sales_rows()))
    con.mark_imported()
    assert not con.pending_files()

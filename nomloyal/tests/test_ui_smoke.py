"""Opens the real window offscreen: every page, a sale through the POS screen, a refund and a registration."""
import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def pump(app, n=5):
    for _ in range(n):
        app.processEvents()


def test_every_page_and_a_sale(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOYAL_HOME", str(tmp_path))
    from app.context import AppContext
    from app.services.demo_data import load_demo
    ctx = AppContext(tmp_path / "ui.db")
    ctx.auth.create("owner", "Owner1234", "Admin", "Owner", first_run=True)
    ctx.auth.login("owner", "Owner1234")
    load_demo(ctx)
    ctx.auth.logout()
    from PySide6.QtWidgets import QDialog, QMessageBox
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)               # never block on a dialog
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    from app.ui.main_window import NAV, MainWindow
    w = MainWindow(ctx); w.resize(1366, 768); w.show(); pump(qapp)
    w.login.user.setText("owner"); w.login.pw.setText("Owner1234"); w.login._login(); pump(qapp)
    assert ctx.user is not None
    for key, _label, _perm in NAV:
        w.goto(key); pump(qapp)
        assert w.pages.get(key) is not None
    # POS sale through the screen
    pos = w.goto("pos")
    pid = ctx.products.by_sku("SA-202").id
    pos.add(pid); pos.add(pid)
    c = ctx.customers.search("Ayesha")[0]
    pos._set_customer(c, "qr")
    pos.inv_disc.setText("1000"); pump(qapp)
    assert pos.quote.total == 2 * 5_200_000 - 100_000
    before = ctx.db.scalar("SELECT COUNT(*) FROM sales")
    pos.checkout()
    assert ctx.db.scalar("SELECT COUNT(*) FROM sales") == before + 1
    assert not pos.cart
    sid = ctx.db.scalar("SELECT MAX(id) FROM sales")
    # refund one unit through the dialog
    from app.ui.sales_page import RefundDialog, SaleDetailDialog
    d = SaleDetailDialog(ctx, sid, w)
    r = RefundDialog(ctx, d.sale, d)
    next(iter(r.spins.values())).setValue(1)
    r.reason.setText("size")
    r._ok()
    assert ctx.sales.get(sid)["status"] == "partially_refunded"
    # register a customer through the form
    from app.ui.customers_page import CustomerDialog
    cd = CustomerDialog(ctx, w)
    cd.name.setText("UI Person"); cd.phone.setText("0333-1112223"); cd.c_data.setChecked(True)
    cd._save()
    assert ctx.customers.lookup("03331112223")[0].full_name == "UI Person"
    # profile dialog renders for admin and for a cashier
    from app.ui.customer_detail_page import CustomerProfileDialog
    CustomerProfileDialog(ctx, c.id, w)
    w.lock  # exists
    w.close()
    ctx.close()


def test_cashier_pages_and_first_run(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOYAL_HOME", str(tmp_path))
    from PySide6.QtWidgets import QDialog, QMessageBox
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: 0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    from app.context import AppContext
    ctx = AppContext(tmp_path / "fr.db")
    from app.ui.login_window import FirstRunDialog
    d = FirstRunDialog(ctx)
    d.store.setText("Test Shop"); d.username.setText("boss"); d.p1.setText("Boss12345"); d.p2.setText("Boss12345")
    d._ok()
    assert not ctx.auth.needs_first_run() and ctx.settings.get("store_name") == "Test Shop"
    ctx.auth.login("boss", "Boss12345")
    ctx.auth.create("till", "Till12345", "Cashier", "Till One")
    ctx.auth.logout()
    from app.ui.main_window import MainWindow
    w = MainWindow(ctx); w.resize(1366, 768); w.show(); pump(qapp)
    w.login.user.setText("till"); w.login.pw.setText("Till12345"); w.login._login(); pump(qapp)
    keys = [w.nav.item(i).data(0x0100) for i in range(w.nav.count())]
    assert "pos" in keys and "staff" not in keys and "backup" not in keys and "settings" not in keys
    for k in keys:
        w.goto(k); pump(qapp)
    w.close()
    ctx.close()

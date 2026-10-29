"""Transaction history, sale details, refunds, voids, linking a walk-in sale to a customer."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from app.money import fmt
from app.services.reporting_service import range_bounds
from app.ui.reusable_widgets import (DateRange, EmptyState, PageHeader, button, card, confirm, fill_table, guarded, info,
                                     make_table, muted, selected_key, status_color, subtitle, ts)


class RefundDialog(QDialog):
    def __init__(self, ctx, sale: dict, parent=None):
        super().__init__(parent)
        self.ctx, self.sale = ctx, sale
        self.setWindowTitle(f"Refund - {sale['receipt_no']}"); self.resize(640, 460)
        v = QVBoxLayout(self)
        v.addWidget(muted("Choose how many of each item come back. The amount is calculated from what the customer "
                          "paid for those units (discounts and tax included)."))
        self.t = QTableWidget(0, 4); self.t.setHorizontalHeaderLabels(["Item", "Bought", "Already refunded", "Refund now"])
        self.t.verticalHeader().setVisible(False)
        from PySide6.QtWidgets import QHeaderView
        self.t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.spins = {}
        items = sale["items"]
        self.t.setRowCount(len(items))
        for i, it in enumerate(items):
            self.t.setItem(i, 0, QTableWidgetItem(it["name"]))
            self.t.setItem(i, 1, QTableWidgetItem(str(it["qty"])))
            self.t.setItem(i, 2, QTableWidgetItem(str(it["refunded_qty"])))
            sp = QSpinBox(); sp.setRange(0, it["qty"] - it["refunded_qty"])
            self.t.setCellWidget(i, 3, sp); self.spins[it["id"]] = sp
        v.addWidget(self.t, 1)
        f = QFormLayout()
        self.reason = QLineEdit(); self.reason.setPlaceholderText("e.g. wrong size, damaged")
        self.method = QComboBox(); self.method.addItems(ctx.settings.get("payment_methods") or ["Cash"])
        self.restock = QCheckBox("Put the items back into stock"); self.restock.setChecked(True)
        f.addRow("Reason *", self.reason); f.addRow("Refund by", self.method); f.addRow("", self.restock)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Refund"); bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _ok(self):
        q = {iid: sp.value() for iid, sp in self.spins.items() if sp.value()}
        if guarded(self, "Refund", self.ctx.sales.refund, self.sale["id"], q, self.reason.text(), self.method.currentText(),
                   self.restock.isChecked())[0]:
            self.accept()


class SaleDetailDialog(QDialog):
    def __init__(self, ctx, sid: int, parent=None):
        super().__init__(parent)
        self.ctx, self.sid = ctx, sid
        self.setWindowTitle("Sale"); self.resize(820, 600)
        self.v = QVBoxLayout(self); self.v.setContentsMargins(20, 16, 20, 14)
        self.head = QLabel(); self.head.setTextFormat(Qt.RichText); self.head.setWordWrap(True)
        self.v.addWidget(self.head)
        self.items = make_table(["SKU", "Item", "Qty", "Unit price", "Discount", "Tax", "Line total", "Refunded"], 1,
                                sortable=False)
        self.refunds = make_table(["Refund", "When", "Amount", "Reason", "By", "Method"], 3, sortable=False)
        self.v.addWidget(subtitle("Items")); self.v.addWidget(self.items, 2)
        self.v.addWidget(subtitle("Refunds")); self.v.addWidget(self.refunds, 1)
        row = QHBoxLayout()
        self.b_receipt = button("Receipt", icon_name="print"); self.b_receipt.clicked.connect(self._receipt)
        self.b_refund = button("Refund items", "primary", "refresh"); self.b_refund.clicked.connect(self._refund)
        self.b_void = button("Void sale", "danger", "x"); self.b_void.clicked.connect(self._void)
        self.b_link = button("Link to customer", icon_name="customers"); self.b_link.clicked.connect(self._link)
        close = button("Close"); close.clicked.connect(self.accept)
        for b in (self.b_receipt, self.b_refund, self.b_link, self.b_void):
            row.addWidget(b)
        row.addStretch(1); row.addWidget(close)
        self.v.addLayout(row)
        self.refresh()

    def refresh(self):
        ok, s = guarded(self, "Sale", self.ctx.sales.get, self.sid)
        if not ok:
            self.reject(); return
        self.sale = s
        st = s["status"].replace("_", " ").upper()
        cust = f"{s['customer']} ({s['loyalty_id']}) - linked by {s['link_method'].replace('_', ' ')}" if s["customer"] \
            else "Walk-in (no customer)"
        void = f"<br><b style='color:#C2483A'>Voided:</b> {s['void_reason']}" if s["status"] == "voided" else ""
        demo = " <span style='background:#C9A227;padding:2px 6px'>DEMO</span>" if s["is_demo"] else ""
        self.head.setText(f"<span style='font-size:15pt;font-weight:600'>{s['receipt_no']}</span>{demo} &nbsp; "
                          f"<b style='color:{status_color(s['status'])}'>{st}</b><br>{ts(s['sold_at'])} · cashier "
                          f"{s['cashier'] or '-'} · {s['payment_method']} · source {s['source']}<br>Customer: {cust}"
                          f"<br>Subtotal {fmt(s['subtotal'])} · discounts {fmt(s['discount_total'])} · tax "
                          f"{fmt(s['tax_total'])} · <b>total {fmt(s['total'])}</b> · refunded {fmt(s['refunded_total'])}"
                          f"{void}")
        fill_table(self.items, [[i["sku"], i["name"], i["qty"], ("money", i["unit_price"]),
                                 ("money", i["line_discount"] + i["invoice_discount_share"]), ("money", i["line_tax"]),
                                 ("money", i["line_total"]), i["refunded_qty"]] for i in s["items"]])
        fill_table(self.refunds, [[r["refund_no"], ts(r["refunded_at"]), ("money", r["amount"]), r["reason"],
                                   r["processed_by_name"] or "-", r["method"]] for r in s["refunds"]])
        can = self.ctx.can
        open_qty = any(i["qty"] > i["refunded_qty"] for i in s["items"])
        self.b_refund.setVisible(can("sales.refund") and s["status"] != "voided" and open_qty)
        self.b_void.setVisible(can("sales.void") and s["status"] == "completed")
        self.b_link.setVisible(can("sales.refund") and not s["customer_id"] and s["status"] != "voided")

    def _receipt(self):
        from app.ui.pos_page import ReceiptDialog
        ReceiptDialog(self.ctx, self.sid, self).exec()

    def _refund(self):
        if RefundDialog(self.ctx, self.sale, self).exec():
            self.refresh()

    def _void(self):
        if not confirm(self, "Void sale", f"Void {self.sale['receipt_no']}? Stock goes back and the sale no longer counts "
                                          "for reports or VIP status.", True):
            return
        reason, ok = QInputDialog.getText(self, "Void sale", "Reason:")
        if ok and guarded(self, "Void", self.ctx.sales.void, self.sid, reason)[0]:
            self.refresh()

    def _link(self):
        text, ok = QInputDialog.getText(self, "Link to customer", "Loyalty ID, QR text or phone of the customer:")
        if not ok:
            return
        ok2, res = guarded(self, "Link", self.ctx.customers.lookup, text)
        if ok2:
            c, method = res
            if confirm(self, "Link", f"Link {self.sale['receipt_no']} to {c.full_name} ({c.loyalty_id})?"):
                if guarded(self, "Link", self.ctx.sales.link_customer, self.sid, c.id, method)[0]:
                    self.refresh()


class SalesPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Sales & Refunds", "Transactions, refunds and voids")
        lay.addWidget(h)
        bar = QHBoxLayout()
        self.range = DateRange(30); self.range.changed.connect(self.reload)
        self.text = QLineEdit(); self.text.setPlaceholderText("Receipt number or customer"); self.text.returnPressed.connect(self.reload)
        self.status = QComboBox()
        for t, v in (("All statuses", ""), ("Completed", "completed"), ("Partially refunded", "partially_refunded"),
                     ("Refunded", "refunded"), ("Voided", "voided")):
            self.status.addItem(t, v)
        self.status.currentIndexChanged.connect(self.reload)
        go = button("Search", icon_name="search"); go.clicked.connect(self.reload)
        bar.addWidget(self.range); bar.addWidget(self.text, 1); bar.addWidget(self.status); bar.addWidget(go)
        lay.addLayout(bar)
        self.table = make_table(["Receipt", "Date", "Customer", "Cashier", "Payment", "Total", "Refunded", "Status"], 2)
        self.table.doubleClicked.connect(self.open)
        self.empty = EmptyState("No transactions in this period.")
        lay.addWidget(self.table, 1); lay.addWidget(self.empty)
        foot = QHBoxLayout()
        o = button("Open", "primary", "sales"); o.clicked.connect(self.open)
        self.summary = muted()
        foot.addWidget(o); foot.addStretch(1); foot.addWidget(self.summary)
        lay.addLayout(foot)

    def refresh(self):
        self.reload()

    def reload(self):
        t0, t1 = range_bounds(*self.range.range())
        rows = self.ctx.sales.search(t0, t1, self.text.text().strip(), self.status.currentData())
        fill_table(self.table, [[r["receipt_no"] + (" (demo)" if r["is_demo"] else ""), ts(r["sold_at"]),
                                 r["customer"] or "Walk-in", r["cashier"] or "-", r["payment_method"], ("money", r["total"]),
                                 ("money", r["refunded"]), r["status"].replace("_", " ")] for r in rows],
                   [r["id"] for r in rows], {(i, 7): status_color(r["status"]) for i, r in enumerate(rows)})
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)
        valid = [r for r in rows if r["status"] != "voided"]
        self.summary.setText(f"{len(rows)} transaction(s) · net {fmt(sum(r['total'] - r['refunded'] for r in valid))}")

    def open(self):
        sid = selected_key(self.table)
        if sid:
            SaleDetailDialog(self.ctx, sid, self).exec()
            self.reload()

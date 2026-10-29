"""POS billing: products -> cart -> verified customer link -> server-side totals -> receipt."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from app.config import exports_dir
from app.models import CartLine
from app.money import fmt, rate_bp
from app.services.errors import NotFound
from app.ui.reusable_widgets import (Badge, MoneyEdit, PageHeader, button, card, confirm, guarded, info, make_table,
                                     muted, subtitle, ts)


class ReceiptDialog(QDialog):
    def __init__(self, ctx, sid: int, parent=None):
        super().__init__(parent)
        from app.services.receipt import receipt_html
        self.ctx = ctx
        self.sale = ctx.sales.get(sid)
        self.html = receipt_html(self.sale, ctx.settings.all())
        self.setWindowTitle(f"Receipt {self.sale['receipt_no']}")
        self.resize(460, 640)
        v = QVBoxLayout(self)
        view = QTextBrowser(); view.setHtml(self.html); v.addWidget(view, 1)
        row = QHBoxLayout()
        pr = button("Print", "primary", "print"); pr.clicked.connect(self.print_)
        pdf = button("Save PDF", icon_name="download"); pdf.clicked.connect(self.pdf)
        close = button("Close"); close.clicked.connect(self.accept)
        row.addWidget(pr); row.addWidget(pdf); row.addStretch(1); row.addWidget(close)
        v.addLayout(row)

    def _doc(self) -> QTextDocument:
        d = QTextDocument(); d.setHtml(self.html)
        return d

    def print_(self):
        from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
        pr = QPrinter(QPrinter.HighResolution)
        dlg = QPrintPreviewDialog(pr, self)
        dlg.paintRequested.connect(lambda p: self._doc().print_(p))
        dlg.exec()

    def pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        p, _ = QFileDialog.getSaveFileName(self, "Save receipt", str(exports_dir() / f"{self.sale['receipt_no']}.pdf"),
                                           "PDF (*.pdf)")
        if p:
            pr = QPrinter(QPrinter.HighResolution)
            pr.setOutputFormat(QPrinter.PdfFormat)
            pr.setOutputFileName(p)
            self._doc().print_(pr)
            info(self, "Receipt", "PDF saved.")


class CustomerPicker(QDialog):
    """Cashier selects the customer from a search list (counts as verified 'selected' identification)."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx, self.cid = ctx, None
        self.setWindowTitle("Select customer"); self.resize(620, 460)
        v = QVBoxLayout(self)
        self.q = QLineEdit(); self.q.setPlaceholderText("Type a name, loyalty ID or phone"); v.addWidget(self.q)
        self.t = make_table(["Loyalty ID", "Name", "Phone", "Tier"], 1)
        v.addWidget(self.t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Select"); bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.q.textChanged.connect(self._load); self.t.doubleClicked.connect(self._ok)
        self._load()

    def _load(self):
        from app.ui.reusable_widgets import fill_table
        rows = self.ctx.customers.search(self.q.text(), "active", None, 200)
        fill_table(self.t, [[c.loyalty_id, c.full_name, c.masked_phone, c.tier or "-"] for c in rows], [c.id for c in rows])

    def _ok(self):
        from app.ui.reusable_widgets import selected_key
        self.cid = selected_key(self.t)
        if self.cid:
            self.accept()


class PosPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.cart: list[CartLine] = []
        self.customer = None
        self.link_method = "none"
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("POS Billing", "F2 product search · F4 customer · F9 complete sale")
        lay.addWidget(h)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)
        # ---------------- left: products + cart
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 6, 0); lv.setSpacing(8)
        srow = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Scan barcode / type SKU or product name, Enter to add")
        self.search.returnPressed.connect(self._add_from_search)
        self.cat = QComboBox(); self.cat.currentIndexChanged.connect(self._load_products)
        srow.addWidget(self.search, 1); srow.addWidget(self.cat)
        lv.addLayout(srow)
        self.products = QListWidget(); self.products.setMaximumHeight(170)
        self.products.itemDoubleClicked.connect(lambda it: self.add(it.data(Qt.UserRole)))
        self.search.textChanged.connect(lambda _t: self._t.start())
        self._t = QTimer(self); self._t.setSingleShot(True); self._t.setInterval(200); self._t.timeout.connect(self._load_products)
        lv.addWidget(self.products)
        lv.addWidget(subtitle("Bill"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Item", "Qty", "Unit price", "Line discount", "Line total", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader(); hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.cart_empty = muted("The bill is empty. Scan or search for a product.")
        self.cart_empty.setAlignment(Qt.AlignCenter)
        lv.addWidget(self.table, 1); lv.addWidget(self.cart_empty)
        split.addWidget(left)
        # ---------------- right: customer + totals + payment (scrolls on short screens instead of squeezing)
        right = QWidget()
        rv = QVBoxLayout(right); rv.setContentsMargins(6, 0, 0, 0); rv.setSpacing(8)
        cust = card(subtitle("Customer"))
        self.lookup = QLineEdit(); self.lookup.setPlaceholderText("Loyalty ID, QR scan or phone")
        self.lookup.returnPressed.connect(self.find_customer)
        lrow = QHBoxLayout()
        f = button("Find", icon_name="search"); f.clicked.connect(self.find_customer)
        f.setToolTip("Find by loyalty ID, QR or phone (Enter)"); f.setText("")
        sel = button("", icon_name="customers", tip="Select from the customer list"); sel.clicked.connect(self.pick_customer)
        new = button("", icon_name="plus", tip="Register a new customer"); new.clicked.connect(self.new_customer)
        lrow.addWidget(self.lookup, 1); lrow.addWidget(f); lrow.addWidget(sel); lrow.addWidget(new)
        cust.layout().addLayout(lrow)
        self.cust_box = QLabel(); self.cust_box.setWordWrap(True); self.cust_box.setTextFormat(Qt.RichText)
        self.badge = Badge()
        crow = QHBoxLayout(); crow.addWidget(self.cust_box, 1); crow.addWidget(self.badge, 0, Qt.AlignTop)
        cust.layout().addLayout(crow)
        self.unlink = button("Remove customer", icon_name="x"); self.unlink.clicked.connect(self.clear_customer)
        self.profile_btn = button("Open profile"); self.profile_btn.clicked.connect(
            lambda: self.customer and self.main.open_customer(self.customer.id))
        urow = QHBoxLayout(); urow.addWidget(self.profile_btn); urow.addWidget(self.unlink); urow.addStretch(1)
        cust.layout().addLayout(urow)
        rv.addWidget(cust)
        tot = card(subtitle("Totals"))
        form = QFormLayout(); form.setSpacing(6)
        self.l_sub, self.l_disc, self.l_tax = QLabel(), QLabel(), QLabel()
        for l in (self.l_sub, self.l_disc, self.l_tax):
            l.setAlignment(Qt.AlignRight)
        drow = QHBoxLayout()
        self.inv_disc = MoneyEdit("0"); self.inv_disc.setMaximumWidth(110)
        self.disc_mode = QComboBox(); self.disc_mode.addItem("amount", "amt"); self.disc_mode.addItem("%", "pct")
        self.inv_disc.textChanged.connect(self.recalc); self.disc_mode.currentIndexChanged.connect(self.recalc)
        drow.addWidget(self.inv_disc); drow.addWidget(self.disc_mode)
        form.addRow("Subtotal", self.l_sub); form.addRow("Bill discount", drow); form.addRow("Discounts", self.l_disc)
        self.tax_lbl = QLabel("Tax"); form.addRow(self.tax_lbl, self.l_tax)
        tot.layout().addLayout(form)
        self.l_total = QLabel(); self.l_total.setObjectName("bigTotal"); self.l_total.setAlignment(Qt.AlignRight)
        tot.layout().addWidget(self.l_total)
        self.err = QLabel(); self.err.setStyleSheet("color:#C2483A;"); self.err.setWordWrap(True)
        tot.layout().addWidget(self.err)
        rv.addWidget(tot)
        pay = card(subtitle("Payment"))
        self.payment = QComboBox()
        self.notes = QLineEdit(); self.notes.setPlaceholderText("Note on the bill (optional)")
        pay.layout().addWidget(self.payment); pay.layout().addWidget(self.notes)
        self.complete = button("Complete sale  (F9)", "primary", "check"); self.complete.setMinimumHeight(44)
        self.complete.clicked.connect(self.checkout)
        clear = button("Clear bill", icon_name="trash"); clear.clicked.connect(self.clear)
        pay.layout().addWidget(self.complete); pay.layout().addWidget(clear)
        rv.addWidget(pay); rv.addStretch(1)
        from PySide6.QtWidgets import QFrame, QScrollArea
        rscroll = QScrollArea(); rscroll.setWidget(right); rscroll.setWidgetResizable(True)
        rscroll.setFrameShape(QFrame.NoFrame); rscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rscroll.setMinimumWidth(340); rscroll.setMaximumWidth(440)
        split.addWidget(rscroll)
        split.setStretchFactor(0, 3); split.setStretchFactor(1, 2)
        QShortcut(QKeySequence("F2"), self, self.search.setFocus)
        QShortcut(QKeySequence("F4"), self, self.lookup.setFocus)
        QShortcut(QKeySequence("F9"), self, self.checkout)
        self._show_customer()
        self.recalc()

    # ------------------------------------------------------------------ products
    def refresh(self):
        s = self.ctx.settings
        cur = self.payment.currentText()
        self.payment.clear(); self.payment.addItems(s.get("payment_methods") or ["Cash"])
        if cur:
            self.payment.setCurrentText(cur)
        self.tax_lbl.setText(s.get("tax_label") or "Tax")
        c = self.cat.currentData()
        self.cat.blockSignals(True); self.cat.clear(); self.cat.addItem("All categories", "")
        for k in self.ctx.products.categories():
            self.cat.addItem(k, k)
        self.cat.setCurrentIndex(max(0, self.cat.findData(c))); self.cat.blockSignals(False)
        self._load_products()
        self.search.setFocus()

    def _load_products(self):
        self.products.clear()
        for p in self.ctx.products.search(self.search.text(), self.cat.currentData() or "", True, 200):
            stock = f"  ·  stock {p.stock_qty}" if p.track_stock else ""
            it = QListWidgetItem(f"{p.name}   ·   {p.sku}   ·   {fmt(p.unit_price)}{stock}")
            it.setData(Qt.UserRole, p.id)
            self.products.addItem(it)

    def _add_from_search(self):
        text = self.search.text().strip()
        if not text:
            return
        p = self.ctx.products.by_sku(text)
        if p is None and self.products.count() == 1:
            p = self.ctx.products.get(self.products.item(0).data(Qt.UserRole))
        if p is None:
            self.err.setText("Type the exact SKU / scan the barcode, or double-click a product in the list.")
            return
        self.add(p.id)
        self.search.clear()

    def add(self, pid: int):
        for cl in self.cart:
            if cl.product_id == pid:
                cl.qty += 1
                break
        else:
            self.cart.append(CartLine(pid, 1))
        self.rebuild()

    def has_cart(self) -> bool:
        return bool(self.cart)

    # ------------------------------------------------------------------ cart table
    def rebuild(self):
        self.table.setRowCount(0)                 # drops the old cell widgets
        self.table.setRowCount(len(self.cart))
        for i, cl in enumerate(self.cart):
            p = self.ctx.products.get(cl.product_id)
            name = QTableWidgetItem(p.name); name.setToolTip(f"{p.name} ({p.sku})")
            self.table.setItem(i, 0, name)
            qty = QSpinBox(); qty.setRange(1, 9999); qty.setValue(cl.qty)
            qty.valueChanged.connect(lambda v, k=i: self._set_qty(k, v))
            self.table.setCellWidget(i, 1, qty)
            up = QTableWidgetItem(fmt(p.unit_price)); up.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, up)
            disc = MoneyEdit("0"); disc.set_minor(cl.line_discount or None); disc.setMaximumWidth(110)
            disc.editingFinished.connect(lambda k=i, w=disc: self._set_disc(k, w))
            self.table.setCellWidget(i, 3, disc)
            rm = button("", icon_name="x", tip="Remove"); rm.setFixedWidth(36)
            rm.clicked.connect(lambda _c=False, k=i: self._remove(k))
            self.table.setCellWidget(i, 5, rm)
        self.recalc()

    def _set_qty(self, i, v):
        if i < len(self.cart):
            self.cart[i].qty = v
            self.recalc()

    def _set_disc(self, i, w):
        try:
            self.cart[i].line_discount = w.value()
        except ValueError:
            w.set_minor(None); self.cart[i].line_discount = 0
        self.recalc()

    def _remove(self, i):
        if i < len(self.cart):
            self.cart.pop(i)
            self.rebuild()

    def _invoice_discount(self, subtotal_after_lines: int) -> int:
        if self.disc_mode.currentData() == "pct":
            bp = rate_bp(self.inv_disc.text() or "0")
            from app.money import pct_of
            return pct_of(subtotal_after_lines, bp)
        return self.inv_disc.value()

    def recalc(self):
        self.table.setVisible(bool(self.cart)); self.cart_empty.setVisible(not self.cart)
        self.err.setText("")
        self.quote = None
        if not self.cart:
            for l in (self.l_sub, self.l_disc, self.l_tax):
                l.setText(fmt(0))
            self.l_total.setText(fmt(0)); self.complete.setEnabled(False)
            return
        try:
            base = self.ctx.sales.quote(self.cart, 0)
            inv = self._invoice_discount(base.subtotal - base.discount_total)
            q = self.ctx.sales.quote(self.cart, inv)       # all pricing by the service
            self.quote, self.inv_amount = q, inv
            for i, l in enumerate(q.lines):
                it = QTableWidgetItem(fmt(l.line_total)); it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, 4, it)
            self.l_sub.setText(fmt(q.subtotal)); self.l_disc.setText("-" + fmt(q.discount_total))
            self.l_tax.setText(fmt(q.tax_total)); self.l_total.setText(fmt(q.total))
            self.complete.setEnabled(True)
        except Exception as exc:  # noqa: BLE001 - validation messages are shown inline
            self.err.setText(str(exc)); self.l_total.setText("-"); self.complete.setEnabled(False)

    # ------------------------------------------------------------------ customer
    def find_customer(self):
        try:
            c, method = self.ctx.customers.lookup(self.lookup.text())
        except NotFound as exc:
            self.err.setText(str(exc))
            if confirm(self, "Customer not found", f"{exc}\n\nRegister a new customer?"):
                self.new_customer(self.lookup.text() if self.lookup.text().strip()[:1].isdigit() else "")
            return
        self._set_customer(c, method)

    def pick_customer(self):
        d = CustomerPicker(self.ctx, self)
        if d.exec() and d.cid:
            self._set_customer(self.ctx.customers.get(d.cid), "selected")

    def new_customer(self, phone: str = ""):
        from app.ui.customers_page import CustomerDialog
        d = CustomerDialog(self.ctx, self, prefill_phone=phone if isinstance(phone, str) else "")
        if d.exec():
            self._set_customer(d.result_customer, "selected")

    def _set_customer(self, c, method: str):
        self.customer, self.link_method = c, method
        self.lookup.clear()
        self._show_customer()

    def clear_customer(self):
        self.customer, self.link_method = None, "none"
        self._show_customer()

    def _show_customer(self):
        c = self.customer
        self.unlink.setVisible(bool(c)); self.profile_btn.setVisible(bool(c))
        if not c:
            self.cust_box.setText("<span style='color:#5F6F82'>Walk-in sale (no customer). Link a customer to record "
                                  "the purchase in their history.</span>")
            self.badge.set("", "#000")
            return
        st = self.ctx.reports.customer_stats(c.id)
        how = {"loyalty_id": "loyalty ID", "phone": "phone number", "qr": "QR code", "selected": "selection"}[self.link_method]
        notes = (c.notes[:120] + "…") if len(c.notes) > 120 else c.notes
        self.cust_box.setText(f"<b>{c.full_name}</b>{' (demo)' if c.is_demo else ''}<br>{c.loyalty_id} · identified by {how}"
                              f"<br>Last purchase: {ts(st['last_purchase'], False)}"
                              + (f"<br><i>{notes}</i>" if notes else ""))
        self.badge.set(c.tier or "", self.ctx.vip.tier_color(c.tier))

    # ------------------------------------------------------------------ checkout
    def checkout(self):
        if not self.cart or self.quote is None:
            return
        cid = self.customer.id if self.customer else None
        ok, sid = guarded(self, "Sale", self.ctx.sales.checkout, self.cart, self.payment.currentText(), cid,
                          self.link_method, self.inv_amount, self.notes.text())
        if not ok:
            return
        self.clear(ask=False)
        self.main.refresh_badges()
        ReceiptDialog(self.ctx, sid, self).exec()

    def clear(self, ask: bool = True):
        if ask and self.cart and not confirm(self, "Clear bill", "Remove all items from this bill?"):
            return
        self.cart.clear(); self.inv_disc.clear(); self.notes.clear()
        self.clear_customer()
        self.rebuild()
        self.search.setFocus()

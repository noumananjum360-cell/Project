"""Products and basic stock."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
                               QLineEdit, QSpinBox, QVBoxLayout, QWidget)

from app.money import fmt, fmt_rate, rate_bp
from app.ui.reusable_widgets import (EmptyState, MoneyEdit, PageHeader, button, fill_table, guarded, info, make_table,
                                     muted, selected_key)
from app.ui.theme import CRIT


class ProductDialog(QDialog):
    def __init__(self, ctx, parent=None, product=None):
        super().__init__(parent)
        self.ctx, self.p = ctx, product
        self.setWindowTitle("Edit product" if product else "New product"); self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.sku, self.name = QLineEdit(), QLineEdit()
        self.cat = QComboBox(); self.cat.setEditable(True); self.cat.addItems(ctx.products.categories() or ["General"])
        self.price = MoneyEdit("0")
        self.tax = QLineEdit(); self.tax.setPlaceholderText(f"empty = store default ({fmt_rate(ctx.settings.get('tax_rate_bp'))})")
        self.stock = QSpinBox(); self.stock.setRange(-100000, 1_000_000)
        self.track = QCheckBox("Track stock"); self.track.setChecked(True)
        self.active = QCheckBox("For sale (active)"); self.active.setChecked(True)
        f.addRow("SKU / barcode *", self.sku); f.addRow("Name *", self.name); f.addRow("Category", self.cat)
        f.addRow("Unit price (before tax) *", self.price); f.addRow("Tax rate %", self.tax)
        f.addRow("Stock", self.stock); f.addRow("", self.track); f.addRow("", self.active)
        v.addLayout(f)
        if product:
            self.sku.setText(product.sku); self.name.setText(product.name); self.cat.setCurrentText(product.category)
            self.price.set_minor(product.unit_price); self.stock.setValue(product.stock_qty)
            self.tax.setText("" if product.tax_rate_bp is None else str(product.tax_rate_bp / 100))
            self.track.setChecked(product.track_stock); self.active.setChecked(product.active)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject); v.addWidget(bb)

    def _save(self):
        try:
            price = self.price.value()
            tax = rate_bp(self.tax.text()) if self.tax.text().strip() else None
        except ValueError as exc:
            info(self, "Product", str(exc)); return
        if guarded(self, "Product", self.ctx.products.save, self.sku.text(), self.name.text(), self.cat.currentText(),
                   price, tax, self.stock.value(), self.track.isChecked(), self.active.isChecked(),
                   self.p.id if self.p else None)[0]:
            self.accept()


class ProductsPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Products", "Catalogue, prices and stock")
        self.b_new = h.add(button("New product", "primary", "plus")); self.b_new.clicked.connect(self.new)
        lay.addWidget(h)
        bar = QHBoxLayout()
        self.q = QLineEdit(); self.q.setPlaceholderText("Search SKU or name"); self.q.textChanged.connect(self.reload)
        self.cat = QComboBox(); self.cat.currentIndexChanged.connect(self.reload)
        self.inactive = QCheckBox("Show inactive"); self.inactive.toggled.connect(self.reload)
        bar.addWidget(self.q, 1); bar.addWidget(self.cat); bar.addWidget(self.inactive)
        lay.addLayout(bar)
        self.table = make_table(["SKU", "Name", "Category", "Price", "Tax", "Stock", "Status"], 1)
        self.table.doubleClicked.connect(self.edit)
        self.empty = EmptyState("No products yet. Add products here or import them under Import & POS.")
        lay.addWidget(self.table, 1); lay.addWidget(self.empty)
        foot = QHBoxLayout()
        self.b_edit = button("Edit", icon_name="edit"); self.b_edit.clicked.connect(self.edit)
        self.b_stock = button("Adjust stock", icon_name="products"); self.b_stock.clicked.connect(self.adjust)
        self.b_act = button("Activate / deactivate", icon_name="archive"); self.b_act.clicked.connect(self.toggle)
        for b in (self.b_edit, self.b_stock, self.b_act):
            foot.addWidget(b)
        foot.addStretch(1); self.count = muted(); foot.addWidget(self.count)
        lay.addLayout(foot)

    def refresh(self):
        can = self.ctx.can("products.manage")
        for b in (self.b_new, self.b_edit, self.b_stock, self.b_act):
            b.setVisible(can)
        cur = self.cat.currentData()
        self.cat.blockSignals(True); self.cat.clear(); self.cat.addItem("All categories", "")
        for c in self.ctx.products.categories():
            self.cat.addItem(c, c)
        self.cat.setCurrentIndex(max(0, self.cat.findData(cur))); self.cat.blockSignals(False)
        self.reload()

    def reload(self):
        rows = self.ctx.products.search(self.q.text(), self.cat.currentData() or "", not self.inactive.isChecked(), 5000)
        default = self.ctx.settings.get("tax_rate_bp")
        fill_table(self.table, [[p.sku, p.name + (" (demo)" if p.is_demo else ""), p.category, ("money", p.unit_price),
                                 fmt_rate(p.tax_rate_bp) if p.tax_rate_bp is not None else f"default {fmt_rate(default)}",
                                 p.stock_qty if p.track_stock else "not tracked", "active" if p.active else "inactive"]
                                for p in rows], [p.id for p in rows],
                   {(i, 5): CRIT for i, p in enumerate(rows) if p.track_stock and p.stock_qty <= 2})
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)
        self.count.setText(f"{len(rows)} product(s) · red stock = 2 or fewer left")

    def new(self):
        if ProductDialog(self.ctx, self).exec():
            self.refresh()

    def _p(self):
        pid = selected_key(self.table)
        return self.ctx.products.get(pid) if pid else None

    def edit(self):
        p = self._p()
        if p and self.ctx.can("products.manage") and ProductDialog(self.ctx, self, p).exec():
            self.refresh()

    def adjust(self):
        p = self._p()
        if not p:
            return
        delta, ok = QInputDialog.getInt(self, "Adjust stock", f"{p.name}: add (or subtract with -)", 0, -100000, 100000)
        if not ok or not delta:
            return
        reason, ok = QInputDialog.getText(self, "Adjust stock", "Reason (e.g. new delivery, stock count):")
        if ok and guarded(self, "Stock", self.ctx.products.adjust_stock, p.id, delta, reason)[0]:
            self.reload()

    def toggle(self):
        p = self._p()
        if p and guarded(self, "Product", self.ctx.products.set_active, p.id, not p.active)[0]:
            self.reload()

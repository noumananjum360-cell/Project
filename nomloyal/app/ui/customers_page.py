"""Customer directory: search, filter, sort, paginate; register / edit / archive; quick check-in."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget)

from app.config import exports_dir
from app.ui.reusable_widgets import (EmptyState, PageHeader, button, confirm, fill_table, guarded, info, make_table,
                                     muted, selected_key, ts)

PAGE = 100


class CustomerDialog(QDialog):
    """Register a new customer (with consent) or edit an existing one."""

    def __init__(self, ctx, parent=None, customer=None, prefill_phone: str = ""):
        super().__init__(parent)
        self.ctx, self.cust, self.result_customer = ctx, customer, None
        self.setWindowTitle("Edit customer" if customer else "Register customer")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 18, 22, 16)
        f = QFormLayout(); f.setSpacing(8)
        self.name, self.phone, self.email = QLineEdit(), QLineEdit(prefill_phone), QLineEdit()
        self.tags = QLineEdit(); self.tags.setPlaceholderText("e.g. bridal, family, office")
        self.notes = QPlainTextEdit(); self.notes.setPlaceholderText("Service notes (sizes, preferences)"); self.notes.setFixedHeight(70)
        f.addRow("Full name *", self.name); f.addRow("Phone", self.phone); f.addRow("Email", self.email)
        f.addRow("Tags", self.tags); f.addRow("Notes", self.notes)
        lay.addLayout(f)
        if customer:
            self.name.setText(customer.full_name); self.phone.setText(customer.phone); self.email.setText(customer.email)
            self.tags.setText(customer.tags); self.notes.setPlainText(customer.notes)
        else:
            box = QLabel("<b>Consent</b> - read or show the privacy notice to the customer before saving.")
            box.setWordWrap(True)
            lay.addWidget(box)
            self.c_data = QCheckBox("Customer agrees that the store keeps their details and purchase history")
            self.c_mkt = QCheckBox("Customer agrees to receive offers and messages (optional)")
            notice = button("Show privacy notice", icon_name="privacy")
            notice.clicked.connect(lambda: show_privacy_notice(self.ctx, self))
            lay.addWidget(self.c_data); lay.addWidget(self.c_mkt); lay.addWidget(notice, alignment=Qt.AlignLeft)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setObjectName("primary")
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        if self.cust:
            ok, c = guarded(self, "Customer", self.ctx.customers.update, self.cust.id, self.name.text(), self.phone.text(),
                            self.email.text(), self.notes.toPlainText(), self.tags.text())
        else:
            ok, c = guarded(self, "Customer", self.ctx.customers.create, self.name.text(), self.phone.text(),
                            self.email.text(), self.notes.toPlainText(), self.tags.text(), self.c_data.isChecked(),
                            self.c_mkt.isChecked())
        if ok:
            self.result_customer = c
            self.accept()


def show_privacy_notice(ctx, parent):
    from app.ui.privacy_page import privacy_notice_text
    d = QDialog(parent); d.setWindowTitle("Privacy notice"); d.resize(620, 560)
    v = QVBoxLayout(d)
    t = QPlainTextEdit(privacy_notice_text(ctx)); t.setReadOnly(True)
    v.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(d.reject); v.addWidget(bb)
    d.exec()


class CustomersPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.offset = 0
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Customers", "Registered loyalty customers")
        self.b_new = h.add(button("Register customer", "primary", "plus")); self.b_new.clicked.connect(self.new)
        lay.addWidget(h)
        bar = QHBoxLayout(); bar.setSpacing(8)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search name, loyalty ID, phone, email or tag")
        self.search.setClearButtonEnabled(True)
        self._t = QTimer(self); self._t.setSingleShot(True); self._t.setInterval(250)
        self._t.timeout.connect(lambda: self.reload(reset=True))
        self.search.textChanged.connect(self._t.start)
        self.status = QComboBox()
        for text, v in (("Active", "active"), ("Archived", "archived"), ("Deleted (anonymised)", "anonymized"), ("All", None)):
            self.status.addItem(text, v)
        self.tier = QComboBox()
        self.order = QComboBox()
        for text, v in (("Name A-Z", "name"), ("Newest", "newest"), ("Recently updated", "updated")):
            self.order.addItem(text, v)
        for w in (self.status, self.tier, self.order):
            w.currentIndexChanged.connect(lambda _i: self.reload(reset=True))
        bar.addWidget(self.search, 1); bar.addWidget(self.status); bar.addWidget(self.tier); bar.addWidget(self.order)
        lay.addLayout(bar)
        self.table = make_table(["Loyalty ID", "Name", "Phone", "Tier", "Tags", "Registered"], 1)
        self.table.doubleClicked.connect(self.open)
        self.empty = EmptyState("No customers found. Register a customer, or import a customer list under Import & POS.")
        lay.addWidget(self.table, 1); lay.addWidget(self.empty)
        foot = QHBoxLayout(); foot.setSpacing(8)
        self.b_open = button("Open profile", "primary", "customers"); self.b_open.clicked.connect(self.open)
        self.b_edit = button("Edit", icon_name="edit"); self.b_edit.clicked.connect(self.edit)
        self.b_checkin = button("Check in", icon_name="user_check", tip="Record that the customer is in the store")
        self.b_checkin.clicked.connect(self.check_in)
        self.b_arch = button("Archive / restore", icon_name="archive"); self.b_arch.clicked.connect(self.archive)
        self.b_exp = button("Export CSV", icon_name="download"); self.b_exp.clicked.connect(self.export)
        self.prev, self.next = button("‹ Previous"), button("Next ›")
        self.prev.clicked.connect(lambda: self._page(-1)); self.next.clicked.connect(lambda: self._page(1))
        self.count = muted()
        for b in (self.b_open, self.b_edit, self.b_checkin, self.b_arch, self.b_exp):
            foot.addWidget(b)
        foot.addStretch(1); foot.addWidget(self.count); foot.addWidget(self.prev); foot.addWidget(self.next)
        lay.addLayout(foot)

    def refresh(self):
        cur = self.tier.currentData()
        self.tier.blockSignals(True)
        self.tier.clear(); self.tier.addItem("Any tier", None); self.tier.addItem("No tier", "__none__")
        for t in self.ctx.vip.tiers():
            self.tier.addItem(t.name, t.name)
        i = self.tier.findData(cur); self.tier.setCurrentIndex(max(0, i))
        self.tier.blockSignals(False)
        c = self.ctx
        self.b_new.setVisible(c.can("customers.create")); self.b_edit.setVisible(c.can("customers.edit"))
        self.b_arch.setVisible(c.can("customers.archive")); self.b_exp.setVisible(c.can("export.unrestricted"))
        self.reload()

    def _page(self, d):
        self.offset = max(0, self.offset + d * PAGE)
        self.reload()

    def reload(self, reset: bool = False):
        if reset:
            self.offset = 0
        text, st, tier = self.search.text().strip(), self.status.currentData(), self.tier.currentData()
        rows = self.ctx.customers.search(text, st, tier, PAGE + 1, self.offset, self.order.currentData())
        more = len(rows) > PAGE
        rows = rows[:PAGE]
        sensitive = self.ctx.can("customers.view_sensitive")
        colors = {(i, 3): self.ctx.vip.tier_color(c.tier) for i, c in enumerate(rows) if c.tier}
        fill_table(self.table, [[c.loyalty_id + (" (demo)" if c.is_demo else ""), c.full_name,
                                 c.phone if sensitive else c.masked_phone, c.tier or "-", c.tags,
                                 ts(c.created_at, False)] for c in rows], [c.id for c in rows], colors)
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)
        self.count.setText(f"{self.offset + 1}-{self.offset + len(rows)}" if rows else "")
        self.prev.setEnabled(self.offset > 0); self.next.setEnabled(more)

    def _cid(self):
        cid = selected_key(self.table)
        if not cid:
            info(self, "Customers", "Select a customer first.")
        return cid

    def new(self):
        d = CustomerDialog(self.ctx, self)
        if d.exec():
            self.reload()
            self.main.open_customer(d.result_customer.id)

    def open(self):
        cid = self._cid()
        if cid:
            self.main.open_customer(cid)
            self.reload()

    def edit(self):
        cid = self._cid()
        if cid:
            ok, cust = guarded(self, "Customer", self.ctx.customers.get, cid)
            if ok and CustomerDialog(self.ctx, self, cust).exec():
                self.reload()

    def check_in(self):
        cid = self._cid()
        if cid:
            ok, aid = guarded(self, "Check in", self.ctx.customers.check_in, cid, "selected")
            if ok:
                info(self, "Check in", "Visit recorded." + (" A returning-customer alert was raised." if aid else ""))
                self.main.refresh_badges()

    def archive(self):
        cid = self._cid()
        if not cid:
            return
        cust = self.ctx.customers.repo.get(cid)
        arch = cust.status == "active"
        if confirm(self, "Customer", f"{'Archive' if arch else 'Restore'} {cust.full_name}?"):
            if guarded(self, "Customer", self.ctx.customers.set_archived, cid, arch)[0]:
                self.reload()

    def export(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export customers", str(exports_dir() / "customers.csv"), "CSV (*.csv)")
        if p:
            ok, n = guarded(self, "Export", self.ctx.imports.export, "customers", p)
            if ok:
                info(self, "Export", f"{n} customers exported. Keep this file safe - it contains personal data.")

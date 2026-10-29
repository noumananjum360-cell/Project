"""VIP customers and tier rules."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLineEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.money import fmt
from app.ui.reusable_widgets import (EmptyState, MoneyEdit, PageHeader, button, card, confirm, fill_table, guarded, info,
                                     make_table, muted, selected_key, ts)


class TierDialog(QDialog):
    def __init__(self, ctx, parent=None, tier=None):
        super().__init__(parent)
        self.ctx, self.tier = ctx, tier
        self.setWindowTitle("Edit tier" if tier else "New tier"); self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit(tier.name if tier else "")
        self.rank = QSpinBox(); self.rank.setRange(1, 99); self.rank.setValue(tier.rank if tier else 5)
        self.single = MoneyEdit("leave empty = not used"); self.rolling = MoneyEdit("leave empty = not used")
        self.single.set_minor(tier.min_single_purchase if tier else None)
        self.rolling.set_minor(tier.min_rolling_spend if tier else None)
        self.months = QSpinBox(); self.months.setRange(1, 120); self.months.setValue(tier.window_months if tier else 12)
        self.months.setSuffix(" months")
        self.color = tier.color if tier else "#0E7C7B"
        self.color_btn = button("Colour"); self.color_btn.clicked.connect(self._pick)
        self.active = QCheckBox("Active"); self.active.setChecked(tier.active if tier else True)
        f.addRow("Name", self.name); f.addRow("Rank (higher = better)", self.rank)
        f.addRow("Single purchase at least", self.single); f.addRow("OR net spending at least", self.rolling)
        f.addRow("…within the last", self.months); f.addRow("", self.color_btn); f.addRow("", self.active)
        v.addLayout(f)
        v.addWidget(muted("A customer reaches the tier when either threshold is met by valid purchases in the window. "
                          "Voided sales are ignored; refunds are subtracted."))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject); v.addWidget(bb)
        self._paint()

    def _pick(self):
        from PySide6.QtGui import QColor
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name(); self._paint()

    def _paint(self):
        self.color_btn.setStyleSheet(f"background:{self.color}; color:white; font-weight:600;")

    def _save(self):
        try:
            single = self.single.value() if self.single.text().strip() else None
            rolling = self.rolling.value() if self.rolling.text().strip() else None
        except ValueError as exc:
            info(self, "Tier", str(exc)); return
        if guarded(self, "Tier", self.ctx.vip.save_tier, self.name.text(), self.rank.value(), single, rolling,
                   self.months.value(), self.color, self.active.isChecked(), self.tier.id if self.tier else None)[0]:
            self.accept()


class VipPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("VIP Customers", "Tiers are calculated from valid purchases only")
        self.recalc = h.add(button("Recalculate all", icon_name="refresh")); self.recalc.clicked.connect(self._recalc)
        lay.addWidget(h)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs, 1)
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        bar = QHBoxLayout(); self.filter = QComboBox(); self.filter.currentIndexChanged.connect(self.load_customers)
        bar.addWidget(self.filter); bar.addStretch(1)
        self.count = muted(); bar.addWidget(self.count)
        v.addLayout(bar)
        self.table = make_table(["Customer", "Loyalty ID", "Tier", "Net spending", "Last purchase", "Why"], 5)
        self.table.doubleClicked.connect(self._open)
        self.empty = EmptyState("No customers have reached a tier yet.")
        v.addWidget(self.table, 1); v.addWidget(self.empty)
        o = button("Open profile", "primary", "customers"); o.clicked.connect(self._open)
        v.addWidget(o)
        self.tabs.addTab(w, "Customers with a tier")
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.rules = make_table(["Tier", "Rank", "Single purchase", "Net spending", "Window", "Active"], 0, sortable=False)
        self.rules.doubleClicked.connect(self._edit)
        v.addWidget(self.rules, 1)
        v.addWidget(card(muted(
            "Refund policy: refunds are subtracted from the purchase they belong to, so a refund can lower a customer's "
            "tier. Voided sales never count. Manual overrides (from a customer's profile) take precedence and are "
            "recorded in the audit log with the reason.")))
        row = QHBoxLayout()
        self.b_add = button("New tier", "primary", "plus"); self.b_add.clicked.connect(self._add)
        self.b_edit = button("Edit", icon_name="edit"); self.b_edit.clicked.connect(self._edit)
        self.b_del = button("Delete", icon_name="trash"); self.b_del.clicked.connect(self._delete)
        for b in (self.b_add, self.b_edit, self.b_del):
            row.addWidget(b)
        row.addStretch(1)
        self.rules_note = muted()
        row.addWidget(self.rules_note)
        v.addLayout(row)
        self.tabs.addTab(w, "Tier rules")

    def refresh(self):
        cur = self.filter.currentData()
        self.filter.blockSignals(True); self.filter.clear(); self.filter.addItem("All tiers", None)
        for t in self.ctx.vip.tiers():
            self.filter.addItem(t.name, t.name)
        self.filter.setCurrentIndex(max(0, self.filter.findData(cur))); self.filter.blockSignals(False)
        can = self.ctx.can("vip.rules")
        for b in (self.b_add, self.b_edit, self.b_del, self.recalc):
            b.setEnabled(can)
        self.rules_note.setText("" if can else "Only an Admin (or a Manager, if allowed in Store settings) can edit rules.")
        self.load_customers(); self.load_rules()

    def load_customers(self):
        rows = self.ctx.reports.vip_customers()
        if self.filter.currentData():
            rows = [r for r in rows if r["tier"] == self.filter.currentData()]
        fill_table(self.table, [[r["full_name"], r["loyalty_id"], r["tier"] + (" (manual)" if r["overridden"] else ""),
                                 ("money", r["net"] or 0), ts(r["last"], False),
                                 r["vip_override_reason"] if r["overridden"] else r["vip_reason"]] for r in rows],
                   [r["id"] for r in rows], {(i, 2): self.ctx.vip.tier_color(r["tier"]) for i, r in enumerate(rows)})
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)
        self.count.setText(f"{len(rows)} customer(s)")

    def load_rules(self):
        ts_ = self.ctx.vip.tiers()
        fill_table(self.rules, [[t.name, t.rank, fmt(t.min_single_purchase) if t.min_single_purchase else "-",
                                 fmt(t.min_rolling_spend) if t.min_rolling_spend else "-", f"{t.window_months} months",
                                 "yes" if t.active else "no"] for t in sorted(ts_, key=lambda t: t.rank)],
                   [t.id for t in sorted(ts_, key=lambda t: t.rank)],
                   {(i, 0): t.color for i, t in enumerate(sorted(ts_, key=lambda t: t.rank))})

    def _open(self):
        cid = selected_key(self.table)
        if cid:
            self.main.open_customer(cid); self.refresh()

    def _tier(self):
        tid = selected_key(self.rules)
        return next((t for t in self.ctx.vip.tiers() if t.id == tid), None)

    def _add(self):
        if TierDialog(self.ctx, self).exec():
            self.refresh()

    def _edit(self):
        t = self._tier()
        if t and self.ctx.can("vip.rules") and TierDialog(self.ctx, self, t).exec():
            self.refresh()

    def _delete(self):
        t = self._tier()
        if t and confirm(self, "Delete tier", f"Delete the {t.name} tier? Everyone is recalculated."):
            if guarded(self, "Tier", self.ctx.vip.delete_tier, t.id)[0]:
                self.refresh()

    def _recalc(self):
        ok, n = guarded(self, "VIP", self.ctx.vip.recalculate_all, "manual recalculation")
        if ok:
            info(self, "VIP", f"{n} customers recalculated.")
            self.refresh()

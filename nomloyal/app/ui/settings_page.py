"""Store settings: store profile, tax, receipts, payments, loyalty, alerts, security, demo data."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QSpinBox,
                               QVBoxLayout, QWidget)

from app import money
from app.money import fmt_rate, rate_bp
from app.ui.reusable_widgets import PageHeader, button, card, confirm, guarded, info, muted, subtitle


class SettingsPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        s = ctx.settings
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Store Settings")
        sv = h.add(button("Save settings", "primary", "check")); sv.clicked.connect(self.save)
        lay.addWidget(h)
        grid = QGridLayout(); grid.setSpacing(10)
        self.w = {}

        def line(key):
            e = QLineEdit(str(s.get(key) or "")); self.w[key] = e; return e

        def check(key, text):
            e = QCheckBox(text); e.setChecked(bool(s.get(key))); self.w[key] = e; return e

        def spin(key, lo, hi, suffix=""):
            e = QSpinBox(); e.setRange(lo, hi); e.setValue(int(s.get(key) or 0)); e.setSuffix(suffix); self.w[key] = e; return e

        def box(title, r, c, rows):
            f = QFormLayout(); f.setSpacing(8)
            for label, wdg in rows:
                f.addRow(label, wdg)
            cd = card(subtitle(title)); cd.layout().addLayout(f); grid.addWidget(cd, r, c)

        box("Store", 0, 0, [("Store name", line("store_name")), ("Address", line("store_address")),
                            ("Phone", line("store_phone")), ("Currency code", line("currency_code")),
                            ("Currency symbol", line("currency_symbol"))])
        self.tax = QLineEdit(fmt_rate(s.get("tax_rate_bp")).rstrip("%"))
        self.payments = QLineEdit(", ".join(s.get("payment_methods") or []))
        box("Billing", 0, 1, [("Default tax rate %", self.tax), ("Tax label", line("tax_label")),
                              ("Receipt prefix", line("receipt_prefix")), ("Receipt footer", line("receipt_footer")),
                              ("Payment methods", self.payments),
                              ("Max cashier discount", spin("max_discount_pct_cashier", 0, 100, " %")),
                              ("", check("void_same_day_only", "Only an Admin can void a sale from an earlier day"))])
        box("Loyalty & VIP", 1, 0, [("Loyalty ID prefix", line("loyalty_id_prefix")),
                                    ("", check("manager_can_edit_vip_rules", "Managers may edit VIP rules"))])
        box("Alerts & notifications", 1, 1, [
            ("", check("alerts_enabled", "Alert when a registered customer returns")),
            ("Returning = first visit after", spin("alert_returning_after_days", 0, 365, " day(s)")),
            ("Do not repeat an alert within", spin("alert_dedup_minutes", 0, 1440, " min")),
            ("", check("os_notifications", "Windows notifications (no names or purchases are shown)"))])
        self.theme = QComboBox(); self.theme.addItem("Light", "light"); self.theme.addItem("Dark", "dark")
        self.theme.setCurrentIndex(0 if (s.get("theme") or "light") == "light" else 1)
        box("Security & display", 2, 0, [("Lock after inactivity", spin("auto_lock_minutes", 0, 240, " min (0 = never)")),
                                         ("Theme", self.theme)])
        demo = card(subtitle("Demo data"))
        demo.layout().addWidget(muted("Sample customers, products and sales for training. Every sample record is marked "
                                      "DEMO and can be removed without touching real data."))
        row = QHBoxLayout()
        self.b_load = button("Load demo data", icon_name="download"); self.b_load.clicked.connect(self.load_demo)
        self.b_rm = button("Remove demo data", "danger", "trash"); self.b_rm.clicked.connect(self.remove_demo)
        row.addWidget(self.b_load); row.addWidget(self.b_rm); row.addStretch(1)
        demo.layout().addLayout(row)
        grid.addWidget(demo, 2, 1)
        lay.addLayout(grid)
        lay.addStretch(1)

    def refresh(self):
        from app.services.demo_data import has_demo
        d = has_demo(self.ctx.db)
        self.b_load.setEnabled(not d and self.ctx.can("demo.manage")); self.b_rm.setEnabled(d and self.ctx.can("demo.manage"))

    def save(self):
        s = self.ctx.settings
        try:
            tax = rate_bp(self.tax.text() or "0")
        except ValueError as exc:
            info(self, "Settings", str(exc)); return
        pays = [p.strip() for p in self.payments.text().split(",") if p.strip()]
        if not pays:
            info(self, "Settings", "Enter at least one payment method."); return
        changed = {}
        for k, w in self.w.items():
            v = w.isChecked() if isinstance(w, QCheckBox) else (w.value() if isinstance(w, QSpinBox) else w.text().strip())
            if s.get(k) != v:
                s.set(k, v); changed[k] = v
        for k, v in (("tax_rate_bp", tax), ("payment_methods", pays), ("theme", self.theme.currentData())):
            if s.get(k) != v:
                s.set(k, v); changed[k] = v
        money.CURRENCY.update(code=s.get("currency_code"), symbol=s.get("currency_symbol"))
        from app.security.audit import audit
        audit(self.ctx.db, self.ctx.user, "settings_saved", "settings", "store", changed)
        self.main.apply_theme(); self.main.refresh_badges()
        info(self, "Settings", "Saved.")

    def load_demo(self):
        from app.services.demo_data import load_demo
        ok, res = guarded(self, "Demo data", load_demo, self.ctx)
        if ok:
            info(self, "Demo data", f"Loaded {res['customers']} customers, {res['products']} products and "
                                    f"{res['sales']} sales - all marked DEMO.")
            self.refresh(); self.main.refresh_badges()

    def remove_demo(self):
        from app.services.demo_data import remove_demo
        if confirm(self, "Demo data", "Remove all demo records? Real customers, products and sales are kept.", True):
            ok, res = guarded(self, "Demo data", remove_demo, self.ctx)
            if ok:
                info(self, "Demo data", f"Removed {res['customers']} customers, {res['sales']} sales and "
                                        f"{res['products']} products.")
                self.refresh(); self.main.refresh_badges()

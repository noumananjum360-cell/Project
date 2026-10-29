"""Privacy, consent and retention settings; privacy notice template; operator checklist."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout,
                               QWidget)

from app.config import resource_path
from app.ui.reusable_widgets import PageHeader, button, card, guarded, info, muted, subtitle

CHECKLIST = [
    "Read the data-protection and biometric laws that apply to your store (for example Pakistan's data-protection "
    "rules and any provincial requirements) - NomLoyal does not make you compliant automatically.",
    "Adapt the privacy notice below to your store and show it to customers before registering them.",
    "Register customers only with their consent; record withdrawals as soon as they are asked for.",
    "Collect only what you need (name and phone are usually enough).",
    "Set retention periods below and run the retention clean-up regularly.",
    "Give staff the lowest role they need; review the audit log monthly.",
    "Keep backups encrypted and off-site; never e-mail customer exports.",
    "Do NOT enable any biometric recognition without explicit written consent, a documented purpose, a validated "
    "provider and legal advice. Display clear signage if cameras are used.",
    "Answer customer requests (copy of data, correction, deletion) from the customer's profile.",
]


def privacy_notice_text(ctx) -> str:
    t = ctx.settings.get("privacy_notice_text")
    if not t:
        p = resource_path("templates", "privacy_notice_template.md")
        t = p.read_text(encoding="utf-8") if p.exists() else "Privacy notice"
    return t.replace("{{STORE_NAME}}", ctx.settings.get("store_name") or "our store") \
            .replace("{{STORE_PHONE}}", ctx.settings.get("store_phone") or "") \
            .replace("{{STORE_ADDRESS}}", ctx.settings.get("store_address") or "")


class PrivacyPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        s = ctx.settings
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        lay.addWidget(PageHeader("Privacy", "Consent, customer rights and data retention"))
        f = QFormLayout(); f.setSpacing(8)
        self.require = QCheckBox("Require the customer's consent before registering them")
        self.require.setChecked(bool(s.get("require_data_consent")))
        self.version = QLineEdit(s.get("privacy_notice_version") or "1.0")
        self.visits = QSpinBox(); self.visits.setRange(0, 3650); self.visits.setSuffix(" days (0 = keep)")
        self.visits.setValue(int(s.get("retention_visits_days") or 0))
        self.alerts = QSpinBox(); self.alerts.setRange(0, 3650); self.alerts.setSuffix(" days (0 = keep)")
        self.alerts.setValue(int(s.get("retention_alerts_days") or 0))
        self.inactive = QSpinBox(); self.inactive.setRange(0, 240); self.inactive.setSuffix(" months (0 = never)")
        self.inactive.setValue(int(s.get("retention_inactive_customer_months") or 0))
        f.addRow("", self.require); f.addRow("Privacy notice version", self.version)
        f.addRow("Delete visit records after", self.visits); f.addRow("Delete handled alerts after", self.alerts)
        f.addRow("Anonymise customers inactive for", self.inactive)
        c1 = card(subtitle("Settings"))
        c1.layout().addLayout(f)
        row = QHBoxLayout()
        self.save_btn = button("Save", "primary", "check"); self.save_btn.clicked.connect(self.save)
        self.run_btn = button("Run retention clean-up now", icon_name="refresh"); self.run_btn.clicked.connect(self.run)
        row.addWidget(self.save_btn); row.addWidget(self.run_btn); row.addStretch(1)
        c1.layout().addLayout(row)
        c1.layout().addWidget(muted("Sales stay in the accounts when a customer is anonymised; only the personal "
                                    "details are erased. Camera footage is never stored by NomLoyal."))
        lay.addWidget(c1)
        self.notice = QPlainTextEdit(privacy_notice_text(ctx)); self.notice.setMinimumHeight(260)
        c2 = card(subtitle("Privacy notice shown to customers"), self.notice,
                  muted("Edit it for your store. {{STORE_NAME}}, {{STORE_PHONE}} and {{STORE_ADDRESS}} are filled in "
                        "automatically. Increase the version number when you change it."))
        lay.addWidget(c2)
        lay.addWidget(card(subtitle("Customer requests"), muted(
            "Open the customer's profile (Customers) to: export their data (copy of data), correct details (Edit), "
            "record or withdraw consent (Consent tab), or delete / anonymise their data. Every action is in the audit log.")))
        lay.addWidget(card(subtitle("Operator checklist (review before going live)"),
                           muted("".join(f"☐  {x}\n\n" for x in CHECKLIST).strip())))
        lay.addStretch(1)

    def refresh(self):
        can = self.ctx.can("privacy.manage")
        for w in (self.require, self.version, self.visits, self.alerts, self.inactive, self.notice, self.save_btn,
                  self.run_btn):
            w.setEnabled(can)

    def save(self):
        s = self.ctx.settings
        s.set("require_data_consent", self.require.isChecked())
        s.set("privacy_notice_version", self.version.text().strip() or "1.0")
        s.set("retention_visits_days", self.visits.value()); s.set("retention_alerts_days", self.alerts.value())
        s.set("retention_inactive_customer_months", self.inactive.value())
        s.set("privacy_notice_text", self.notice.toPlainText())
        from app.security.audit import audit
        audit(self.ctx.db, self.ctx.user, "privacy_settings_saved", "settings", "privacy",
              {"retention_visits_days": self.visits.value(), "retention_alerts_days": self.alerts.value(),
               "inactive_months": self.inactive.value(), "require_consent": self.require.isChecked()})
        info(self, "Privacy", "Saved.")

    def run(self):
        ok, out = guarded(self, "Retention", self.ctx.privacy.apply_retention, self.ctx.user)
        if ok:
            info(self, "Retention", f"Deleted {out['visits']} visit record(s) and {out['alerts']} alert(s); "
                                    f"anonymised {out['customers']} inactive customer(s).")

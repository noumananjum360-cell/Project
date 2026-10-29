"""Customer profile: summary, purchase timeline, VIP eligibility, consent, loyalty card (QR)."""
from __future__ import annotations

import io

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget)

from app.config import exports_dir
from app.money import fmt
from app.services.privacy_service import CONSENT_TYPES
from app.ui.reusable_widgets import (Badge, KPITile, button, card, confirm, fill_table, guarded, info, make_table, muted,
                                     selected_key, status_color, subtitle, ts)
from app.ui.theme import CRIT, OK


def qr_pixmap(text: str, size: int = 220) -> QPixmap:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathFillImage, border=2)
    buf = io.BytesIO()
    img.save(buf)
    r = QSvgRenderer(QByteArray(buf.getvalue()))
    pm = QPixmap(size, size)
    pm.fill(Qt.white)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


class CustomerProfileDialog(QDialog):
    def __init__(self, ctx, cid: int, parent=None):
        super().__init__(parent)
        self.ctx, self.cid = ctx, cid
        self.setWindowTitle("Customer profile")
        scr = self.screen().availableGeometry() if self.screen() else None
        self.resize(min(1040, int(scr.width() * 0.92)) if scr else 1040, min(720, int(scr.height() * 0.9)) if scr else 720)
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(22, 18, 22, 14); self.lay.setSpacing(10)
        top = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(2)
        self.name = QLabel(); self.name.setObjectName("title")
        self.sub = muted()
        col.addWidget(self.name); col.addWidget(self.sub)
        top.addLayout(col); top.addStretch(1)
        self.badge = Badge(); self.override = muted()
        top.addWidget(self.override, 0, Qt.AlignTop); top.addWidget(self.badge, 0, Qt.AlignTop)
        self.lay.addLayout(top)
        self.kpi_row = QGridLayout(); self.kpi_row.setSpacing(8)
        self.k = {}
        for i, (key, label) in enumerate((("net", "Lifetime net spending"), ("tx", "Purchases"), ("atv", "Avg transaction"),
                                          ("last", "Last purchase"), ("visit", "Last visit"), ("refunds", "Refunds"))):
            self.k[key] = KPITile(label)
            self.kpi_row.addWidget(self.k[key], 0, i)
        self.lay.addLayout(self.kpi_row)
        self.tabs = QTabWidget()
        self.lay.addWidget(self.tabs, 1)
        self._build_tabs()
        row = QHBoxLayout()
        self.b_edit = button("Edit", icon_name="edit"); self.b_edit.clicked.connect(self._edit)
        self.b_checkin = button("Check in", icon_name="user_check"); self.b_checkin.clicked.connect(self._check_in)
        self.b_export = button("Export data", icon_name="download"); self.b_export.clicked.connect(self._export)
        self.b_archive = button("Archive", icon_name="archive"); self.b_archive.clicked.connect(self._archive)
        self.b_delete = button("Delete / anonymise", "danger", "trash"); self.b_delete.clicked.connect(self._delete)
        close = button("Close"); close.clicked.connect(self.accept)
        for b in (self.b_edit, self.b_checkin, self.b_export, self.b_archive, self.b_delete):
            row.addWidget(b)
        row.addStretch(1); row.addWidget(close)
        self.lay.addLayout(row)
        self.refresh()

    def _build_tabs(self):
        # timeline
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.timeline = make_table(["Date", "Event", "Reference", "Details", "Amount", "Status"], 3)
        self.timeline.doubleClicked.connect(self._open_sale)
        self.tl_empty = muted("No purchases or visits yet.")
        v.addWidget(self.timeline); v.addWidget(self.tl_empty)
        self.tabs.addTab(w, "Purchase timeline")
        # service view
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.service = QLabel(); self.service.setWordWrap(True); self.service.setTextFormat(Qt.RichText)
        self.service.setAlignment(Qt.AlignTop)
        v.addWidget(card(self.service)); v.addStretch(1)
        self.tabs.addTab(w, "Service info")
        # VIP
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.vip_text = QLabel(); self.vip_text.setWordWrap(True); self.vip_text.setTextFormat(Qt.RichText)
        self.qual = make_table(["Receipt", "Date", "Paid", "Net after refunds"], 0, sortable=False)
        self.b_override = button("Manual tier change", icon_name="vip"); self.b_override.clicked.connect(self._override)
        v.addWidget(card(self.vip_text)); v.addWidget(subtitle("Qualifying transactions")); v.addWidget(self.qual, 1)
        v.addWidget(self.b_override, alignment=Qt.AlignLeft)
        self.tabs.addTab(w, "VIP status")
        # consent
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.consent_lbl = QLabel(); self.consent_lbl.setTextFormat(Qt.RichText)
        self.consent = make_table(["When", "Consent", "Given", "Notice", "Method", "By", "Notes"], 6, sortable=False)
        crow = QHBoxLayout()
        self.b_grant = button("Record consent", icon_name="check"); self.b_grant.clicked.connect(lambda: self._consent(True))
        self.b_withdraw = button("Record withdrawal", icon_name="x"); self.b_withdraw.clicked.connect(lambda: self._consent(False))
        crow.addWidget(self.b_grant); crow.addWidget(self.b_withdraw); crow.addStretch(1)
        v.addWidget(self.consent_lbl); v.addWidget(self.consent, 1); v.addLayout(crow)
        self.tabs.addTab(w, "Consent")
        # loyalty card
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 8, 0, 0)
        self.qr = QLabel(); self.qr.setAlignment(Qt.AlignCenter)
        self.qr_text = muted(); self.qr_text.setAlignment(Qt.AlignCenter)
        pr = button("Print loyalty card", icon_name="print"); pr.clicked.connect(self._print_card)
        v.addWidget(self.qr); v.addWidget(self.qr_text); v.addWidget(pr, alignment=Qt.AlignCenter); v.addStretch(1)
        self.tabs.addTab(w, "Loyalty card")

    # ------------------------------------------------------------------ data
    def refresh(self):
        ok, c = guarded(self, "Customer", self.ctx.customers.get, self.cid)
        if not ok:
            self.reject(); return
        self.cust = c
        can = self.ctx.can
        sensitive = can("customers.view_sensitive")
        self.name.setText(c.full_name + ("  (demo)" if c.is_demo else ""))
        status = {"archived": " · ARCHIVED", "anonymized": " · DATA DELETED"}.get(c.status, "")
        self.sub.setText(f"Loyalty ID {c.loyalty_id} · phone {c.phone if sensitive else c.masked_phone or '-'}"
                         + (f" · {c.email}" if sensitive and c.email else "") + status)
        self.badge.set(c.tier or "", self.ctx.vip.tier_color(c.tier))
        self.override.setText("manual tier" if c.vip_override_tier else "")
        st = self.ctx.reports.customer_stats(c.id)
        self.k["net"].set(fmt(st["net"]) if sensitive else "-")
        self.k["tx"].set(str(st["transactions"]))
        self.k["atv"].set(fmt(st["atv"]) if sensitive else "-")
        self.k["last"].set(ts(st["last_purchase"], False))
        self.k["visit"].set(ts(st["last_visit"], False))
        self.k["refunds"].set(fmt(st["refunds"]) if sensitive else "-")
        fav = ", ".join(st["favorite_categories"]) or "-"
        self.service.setText(f"<b>Tier:</b> {c.tier or 'none'}<br><b>Favourite categories:</b> {fav}<br>"
                             f"<b>Last purchase:</b> {ts(st['last_purchase'])}<br><b>Last visit:</b> {ts(st['last_visit'])}"
                             f"<br><b>Tags:</b> {c.tags or '-'}<br><br><b>Service notes</b><br>"
                             f"{(c.notes or 'No notes.').replace(chr(10), '<br>')}")
        # timeline and money only for staff allowed to see them
        tl = self.ctx.reports.timeline(c.id) if sensitive else []
        fill_table(self.timeline, [[ts(e["ts"]), e["kind"].title(), e["ref"], e["detail"],
                                    ("money", e["amount"]) if e["amount"] is not None else "", e["status"].replace("_", " ")]
                                   for e in tl], [e["sale_id"] for e in tl],
                   {(i, 5): status_color(e["status"]) for i, e in enumerate(tl) if e["status"]})
        self.timeline.setVisible(bool(tl)); self.tl_empty.setVisible(not tl)
        if not sensitive:
            self.tl_empty.setText("Purchase history is visible to managers and admins.")
        self.tabs.setTabEnabled(0, sensitive); self.tabs.setTabEnabled(2, can("vip.view")); self.tabs.setTabEnabled(3, sensitive)
        if not sensitive:
            self.tabs.setCurrentIndex(1)
        if can("vip.view"):
            e = self.ctx.vip.evaluate(c.id)
            lines = "".join(f"<li>{r}</li>" for r in e.reasons)
            ov = (f"<p><b>Manual override:</b> {c.vip_override_tier} - {c.vip_override_reason}</p>"
                  if c.vip_override_tier else "")
            self.vip_text.setText(f"<b>Calculated tier: {e.tier or 'none'}</b><ul>{lines}</ul>{ov}"
                                  "<p style='color:#5F6F82'>Only valid purchases count: voided sales are ignored and "
                                  "refunds are subtracted.</p>")
            fill_table(self.qual, [[s["receipt_no"], ts(s["sold_at"], False), ("money", s["total"]), ("money", s["net"])]
                                   for s in e.qualifying_sales])
        if sensitive:
            cs = self.ctx.privacy.consent_status(c.id)
            self.consent_lbl.setText(" &nbsp; ".join(
                f"<b>{CONSENT_TYPES[k]}:</b> <span style='color:{OK if v else CRIT}'>{'yes' if v else 'no'}</span>"
                for k, v in cs.items()))
            hist = self.ctx.privacy.consent_history(c.id)
            fill_table(self.consent, [[ts(h["recorded_at"]), CONSENT_TYPES[h["consent_type"]], "yes" if h["granted"] else "no",
                                       h["notice_version"], h["method"], h["recorded_by_name"] or "-", h["notes"]]
                                      for h in hist])
        self.qr.setPixmap(qr_pixmap(self.ctx.customers.qr_payload(c)))
        self.qr_text.setText(f"{c.full_name} · {c.loyalty_id}<br>Scan at the till to identify the customer.")
        active = c.status == "active"
        self.b_edit.setVisible(can("customers.edit") and c.status != "anonymized")
        self.b_checkin.setVisible(active)
        self.b_export.setVisible(can("customers.export"))
        self.b_archive.setVisible(can("customers.archive") and c.status != "anonymized")
        self.b_archive.setText("Archive" if active else "Restore")
        self.b_delete.setVisible(can("customers.delete") and c.status != "anonymized")
        self.b_override.setVisible(can("vip.override") and c.status != "anonymized")
        self.b_grant.setVisible(can("customers.edit")); self.b_withdraw.setVisible(can("customers.edit"))

    # ------------------------------------------------------------------ actions
    def _edit(self):
        from app.ui.customers_page import CustomerDialog
        if CustomerDialog(self.ctx, self, self.cust).exec():
            self.refresh()

    def _check_in(self):
        ok, aid = guarded(self, "Check in", self.ctx.customers.check_in, self.cid, "selected")
        if ok:
            info(self, "Check in", "Visit recorded.")
            self.refresh()

    def _open_sale(self):
        sid = selected_key(self.timeline)
        if sid:
            from app.ui.sales_page import SaleDetailDialog
            SaleDetailDialog(self.ctx, sid, self).exec()
            self.refresh()

    def _override(self):
        names = ["(no override - use calculated tier)"] + [t.name for t in self.ctx.vip.tiers()]
        tier, ok = QInputDialog.getItem(self, "Manual tier change", "Tier:", names, 0, False)
        if not ok:
            return
        reason, ok = QInputDialog.getText(self, "Manual tier change", "Reason (saved in the audit log):")
        if ok:
            if guarded(self, "VIP", self.ctx.vip.override, self.cid, None if tier.startswith("(") else tier, reason)[0]:
                self.refresh()

    def _consent(self, granted: bool):
        types = list(CONSENT_TYPES)
        label, ok = QInputDialog.getItem(self, "Consent", "Consent type:", [CONSENT_TYPES[t] for t in types], 0, False)
        if not ok:
            return
        note, ok = QInputDialog.getText(self, "Consent", "Note (optional):")
        if ok and guarded(self, "Consent", self.ctx.privacy.record_consent, self.cid,
                          types[[CONSENT_TYPES[t] for t in types].index(label)], granted, "in_store", note)[0]:
            self.refresh()

    def _export(self):
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.cust.loyalty_id)
        p, _ = QFileDialog.getSaveFileName(self, "Export customer data", str(exports_dir() / f"customer_{safe}.zip"),
                                           "ZIP (*.zip)")
        if p and guarded(self, "Export", self.ctx.privacy.export_customer, self.cid, p)[0]:
            info(self, "Export", "Customer data exported. Give the file only to the customer.")

    def _archive(self):
        arch = self.cust.status == "active"
        if confirm(self, "Customer", f"{'Archive' if arch else 'Restore'} {self.cust.full_name}?"):
            if guarded(self, "Customer", self.ctx.customers.set_archived, self.cid, arch)[0]:
                self.refresh()

    def _delete(self):
        if not confirm(self, "Delete customer data",
                       f"Delete the personal data of {self.cust.full_name}?\n\nCustomers without purchases are removed. "
                       "Customers with purchases are anonymised: name, phone, email and notes are erased; the sales "
                       "stay in the store's accounts without identifying the person. This cannot be undone.", True):
            return
        reason, ok = QInputDialog.getText(self, "Delete customer data", "Reason (e.g. customer request):")
        if ok:
            ok2, res = guarded(self, "Delete", self.ctx.privacy.delete_customer, self.cid, reason)
            if ok2:
                info(self, "Delete", f"Customer {res}.")
                if res == "deleted":
                    self.accept()
                else:
                    self.refresh()

    def _print_card(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        pr = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(pr, self).exec():
            p = QPainter(pr)
            page = pr.pageRect(QPrinter.DevicePixel)
            w = page.width() * 0.45
            p.drawText(QRectF(0, 0, w, 120), Qt.AlignLeft, f"{self.ctx.settings.get('store_name')}\n"
                                                           f"{self.cust.full_name}\n{self.cust.loyalty_id}")
            p.drawPixmap(QRectF(0, 140, w * 0.6, w * 0.6).toRect(), qr_pixmap(self.ctx.customers.qr_payload(self.cust), 600))
            p.end()

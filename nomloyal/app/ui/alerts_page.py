"""Alert centre + front-desk check-in (loyalty ID / QR / phone). Recognition alerts appear here only when a real,
validated provider is installed; simulated alerts are always labelled."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.services.errors import NotFound
from app.ui.reusable_widgets import (EmptyState, PageHeader, button, card, confirm, fill_table, guarded, info, make_table,
                                     muted, selected_key, status_color, subtitle, ts)


class AlertsPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Alerts", "Returning registered customers")
        self.demo_btn = h.add(button("Create demo alert (simulated)", tip="For training only - clearly labelled"))
        self.demo_btn.clicked.connect(self._demo)
        lay.addWidget(h)
        desk = card(subtitle("Front-desk check-in"))
        row = QHBoxLayout()
        self.lookup = QLineEdit(); self.lookup.setPlaceholderText("Scan the loyalty QR code, or type the loyalty ID / phone")
        self.lookup.returnPressed.connect(self._check_in)
        go = button("Check in", "primary", "user_check"); go.clicked.connect(self._check_in)
        row.addWidget(self.lookup, 1); row.addWidget(go)
        desk.layout().addLayout(row)
        desk.layout().addWidget(muted("Identifies the customer only from their loyalty ID, QR card or phone number. "
                                      "Managers are alerted when a registered customer returns."))
        lay.addWidget(desk)
        bar = QHBoxLayout()
        self.filter = QComboBox()
        for t, v in (("Open", "open"), ("Acknowledged", "acknowledged"), ("Dismissed", "dismissed"), ("All (history)", None)):
            self.filter.addItem(t, v)
        self.filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.filter); bar.addStretch(1)
        lay.addLayout(bar)
        self.table = make_table(["When", "Alert", "Customer", "Tier", "Source", "Status", "Handled by"], 1)
        self.table.doubleClicked.connect(self._open)
        self.empty = EmptyState("No alerts.")
        lay.addWidget(self.table, 1); lay.addWidget(self.empty)
        foot = QHBoxLayout()
        self.b_open = button("Open customer profile", "primary", "customers"); self.b_open.clicked.connect(self._open)
        self.b_ack = button("Acknowledge", icon_name="check"); self.b_ack.clicked.connect(lambda: self._handle("acknowledged"))
        self.b_dis = button("Dismiss", icon_name="x"); self.b_dis.clicked.connect(lambda: self._handle("dismissed"))
        for b in (self.b_open, self.b_ack, self.b_dis):
            foot.addWidget(b)
        foot.addStretch(1)
        lay.addLayout(foot)

    def refresh(self):
        can = self.ctx.can
        self.b_ack.setVisible(can("alerts.handle")); self.b_dis.setVisible(can("alerts.handle"))
        self.b_open.setVisible(can("customers.view"))
        self.demo_btn.setVisible(can("demo.manage"))
        rows = self.ctx.alerts.list(self.filter.currentData())
        src = {"loyalty_id": "Loyalty ID", "phone": "Phone", "qr": "QR code", "selected": "Staff selection",
               "demo": "DEMO (simulated)", "recognition": "Recognition"}
        fill_table(self.table, [[ts(a["created_at"]), a["title"], a["customer"] or "-", a["tier"] or "-",
                                 src.get(a["source"], a["source"]), a["status"], a["handled_by_name"] or "-"]
                                for a in rows], [a["id"] for a in rows],
                   {(i, 5): status_color(a["status"]) for i, a in enumerate(rows)})
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)
        self.main.refresh_badges()

    def _row(self):
        aid = selected_key(self.table)
        if not aid:
            info(self, "Alerts", "Select an alert first.")
            return None
        return next((a for a in self.ctx.alerts.list(None, 2000) if a["id"] == aid), None)

    def _open(self):
        a = self._row()
        if a and a["customer_id"]:
            self.main.open_customer(a["customer_id"], a["id"])
            self.refresh()

    def _handle(self, status):
        a = self._row()
        if a and guarded(self, "Alert", self.ctx.alerts.handle, a["id"], status)[0]:
            self.refresh()

    def _check_in(self):
        try:
            c, method = self.ctx.customers.lookup(self.lookup.text())
        except NotFound as exc:
            info(self, "Check in", str(exc)); return
        ok, aid = guarded(self, "Check in", self.ctx.customers.check_in, c.id, method)
        if ok:
            self.lookup.clear()
            info(self, "Check in", f"Welcome back recorded for {c.full_name}." + ("" if aid else
                 " (No new alert: first visit, or already alerted recently.)"))
            self.refresh()

    def _demo(self):
        from app.ui.pos_page import CustomerPicker
        if not confirm(self, "Demo alert", "This creates a SIMULATED alert for training. No camera or recognition is "
                                           "involved. It will be clearly labelled as simulated. Continue?"):
            return
        d = CustomerPicker(self.ctx, self)
        if d.exec() and d.cid:
            import time
            # make sure the simulated visit counts as "returning"
            self.ctx.db.execute("INSERT INTO customer_visits(customer_id, visited_at, method, notes, is_demo, created_at) "
                                "VALUES (?,?,?,?,1,?)", (d.cid, time.time() - 10 * 86400, "demo", "simulated history",
                                                          time.time()))
            self.ctx.settings.set("alert_dedup_minutes", self.ctx.settings.get("alert_dedup_minutes"))
            guarded(self, "Demo", self.ctx.customers.check_in, d.cid, "demo", "SIMULATED demo alert", True)
            self.refresh()

"""Dashboard - every number is a live database query. Demo data is clearly labelled."""
from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.money import fmt
from app.ui.reusable_widgets import (BarChart, KPITile, PageHeader, button, card, demo_badge, fill_table, make_table,
                                     muted, status_color, subtitle, ts)
from app.ui.theme import CHART_2, palette


class DashboardPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        self.header = PageHeader("Dashboard", "Today at a glance")
        self.demo = self.header.add(demo_badge("DEMO DATA - figures include sample records"))
        rb = self.header.add(button("Refresh", icon_name="refresh")); rb.clicked.connect(self.refresh)
        lay.addWidget(self.header)
        grid = QGridLayout(); grid.setSpacing(10)
        self.k = {}
        for i, (key, label) in enumerate((("today_sales", "Today's net sales"), ("month_sales", "This month (net)"),
                                          ("atv", "Avg transaction (month)"), ("customers", "Registered customers"),
                                          ("returning", "Returning customers"), ("repeat_pct", "Repeat-customer rate"),
                                          ("vip", "Customers with a tier"), ("open_alerts", "Pending alerts"))):
            self.k[key] = KPITile(label)
            grid.addWidget(self.k[key], i // 4, i % 4)
        lay.addLayout(grid)
        charts = QHBoxLayout(); charts.setSpacing(10)
        self.trend = BarChart(True, "No sales in the last 14 days")
        self.cats = BarChart(True, "No sales in the last 30 days")
        self.cats.color = CHART_2
        charts.addWidget(card(subtitle("Net sales - last 14 days"), self.trend), 3)
        charts.addWidget(card(subtitle("Top categories - last 30 days"), self.cats), 2)
        lay.addLayout(charts)
        lists = QGridLayout(); lists.setSpacing(10)
        self.t_sales = make_table(["Receipt", "Time", "Customer", "Total", "Status"], 2, sortable=False)
        self.t_act = make_table(["When", "Customer", "Tier", "How"], 1, sortable=False)
        self.t_ref = make_table(["Refund", "When", "Receipt", "Amount", "Reason"], 4, sortable=False)
        self.t_alerts = make_table(["When", "Alert", "Customer"], 1, sortable=False)
        for t in (self.t_sales, self.t_act, self.t_ref, self.t_alerts):
            t.setMinimumHeight(190)
        self.t_sales.doubleClicked.connect(self._open_sale)
        self.t_act.doubleClicked.connect(self._open_customer)
        self.t_alerts.doubleClicked.connect(lambda: self.main.goto("alerts"))
        self.e_sales, self.e_act = muted("No transactions yet."), muted("No customer activity yet.")
        self.e_ref, self.e_alerts = muted("No refunds."), muted("No pending alerts.")
        lists.addWidget(card(subtitle("Recent transactions"), self.t_sales, self.e_sales), 0, 0)
        lists.addWidget(card(subtitle("Recent customer activity"), self.t_act, self.e_act), 0, 1)
        lists.addWidget(card(subtitle("Pending customer alerts"), self.t_alerts, self.e_alerts), 1, 0)
        lists.addWidget(card(subtitle("Recent refunds"), self.t_ref, self.e_ref), 1, 1)
        lay.addLayout(lists)
        lay.addStretch(1)

    def refresh(self):
        d = self.ctx.reports.dashboard()
        self.demo.setVisible(d["has_demo"])
        for key in ("today_sales", "month_sales", "atv"):
            self.k[key].set(fmt(d[key]))
        self.k["today_sales"].label.setText(f"TODAY'S NET SALES · {d['today_count']} BILL(S)")
        self.k["customers"].set(f"{d['customers']:,}")
        self.k["returning"].set(f"{d['returning']:,}")
        self.k["repeat_pct"].set(f"{d['repeat_pct']:.0f}%")
        self.k["vip"].set(f"{d['vip']:,}")
        self.k["open_alerts"].set(str(d["open_alerts"]), "#C98A2E" if d["open_alerts"] else None)
        self.trend.set_data([dt.date.fromisoformat(k).strftime("%d %b") for k, _ in d["trend"]],
                            [max(0, v) for _, v in d["trend"]], palette()["accent"])
        self.cats.set_data([c["category"] for c in d["top_categories"]], [max(0, c["net"] or 0) for c in d["top_categories"]])
        rs = d["recent_sales"]
        fill_table(self.t_sales, [[r["receipt_no"] + (" (demo)" if r["is_demo"] else ""), ts(r["sold_at"]),
                                   r["customer"] or "Walk-in", ("money", r["total"]), r["status"].replace("_", " ")]
                                  for r in rs], [r["id"] for r in rs],
                   {(i, 4): status_color(r["status"]) for i, r in enumerate(rs)})
        act = d["recent_activity"]
        fill_table(self.t_act, [[ts(a["visited_at"]), a["customer"], a["tier"] or "-",
                                 a["method"].replace("_", " ")] for a in act], [a["customer_id"] for a in act])
        rf = d["recent_refunds"]
        fill_table(self.t_ref, [[r["refund_no"], ts(r["refunded_at"]), r["receipt_no"], ("money", r["amount"]), r["reason"]]
                                for r in rf])
        al = self.ctx.alerts.list("open", 8) if self.ctx.can("alerts.view") else []
        fill_table(self.t_alerts, [[ts(a["created_at"]), a["title"], a["customer"] or "-"] for a in al])
        for t, e, rows in ((self.t_sales, self.e_sales, rs), (self.t_act, self.e_act, act), (self.t_ref, self.e_ref, rf),
                           (self.t_alerts, self.e_alerts, al)):
            t.setVisible(bool(rows)); e.setVisible(not rows)

    def _open_sale(self):
        from app.ui.reusable_widgets import selected_key
        sid = selected_key(self.t_sales)
        if sid:
            from app.ui.sales_page import SaleDetailDialog
            SaleDetailDialog(self.ctx, sid, self).exec()
            self.refresh()

    def _open_customer(self):
        from app.ui.reusable_widgets import selected_key
        cid = selected_key(self.t_act)
        if cid:
            self.main.open_customer(cid)
            self.refresh()

"""Sales and customer analytics with date ranges and CSV export."""
from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from app.config import exports_dir
from app.money import fmt
from app.services.reporting_service import range_bounds
from app.ui.reusable_widgets import (BarChart, DateRange, EmptyState, KPITile, PageHeader, button, card, fill_table,
                                     guarded, info, make_table, muted, subtitle, ts)

REPORTS = [("summary", "Sales summary (daily & monthly)"), ("products", "Sales by product"),
           ("categories", "Sales by category"), ("top", "Top-selling products"), ("repeat", "Repeat customers"),
           ("vip", "VIP customers"), ("clv", "Customer lifetime value"), ("refunds", "Refunds"),
           ("retention", "Customer retention")]


class ReportsPage(QWidget):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.rows, self.cols = [], []
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        h = PageHeader("Analytics", "Reports from real transactions (voided sales excluded, refunds subtracted)")
        self.exp = h.add(button("Export CSV", icon_name="download")); self.exp.clicked.connect(self.export)
        lay.addWidget(h)
        bar = QHBoxLayout()
        self.kind = QComboBox()
        for k, t in REPORTS:
            self.kind.addItem(t, k)
        self.range = DateRange(30)
        self.kind.currentIndexChanged.connect(self.refresh); self.range.changed.connect(self.refresh)
        bar.addWidget(self.kind); bar.addWidget(self.range); bar.addStretch(1)
        lay.addLayout(bar)
        self.kpis = QGridLayout(); self.kpis.setSpacing(8)
        self.k = {}
        for i, (key, label) in enumerate((("a", ""), ("b", ""), ("c", ""), ("d", ""))):
            self.k[key] = KPITile(label); self.kpis.addWidget(self.k[key], 0, i)
        lay.addLayout(self.kpis)
        self.chart = BarChart(True)
        self.chart_card = card(subtitle(""), self.chart)
        lay.addWidget(self.chart_card)
        self.table = make_table([""], 0)
        self.table.setMinimumHeight(260)
        self.empty = EmptyState("No data for this period.")
        lay.addWidget(self.table, 1); lay.addWidget(self.empty)
        self.note = muted(); lay.addWidget(self.note)

    def _kpi(self, vals: list[tuple[str, str]]):
        for (key, tile), v in zip(self.k.items(), vals + [("", "")] * 4):
            tile.setVisible(bool(v[0]))
            tile.label.setText(v[0].upper()); tile.set(v[1])

    def _table(self, cols: list[tuple[str, str]], rows: list[dict], money: set[str] = frozenset(), when: set[str] = frozenset()):
        self.cols, self.rows = cols, rows
        self.table.clear(); self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels([h for _k, h in cols])
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1 if len(cols) > 1 else 0, QHeaderView.Stretch)
        fill_table(self.table, [[("money", r.get(k) or 0) if k in money else (ts(r.get(k), False) if k in when else r.get(k))
                                 for k, _h in cols] for r in rows])
        self.table.setVisible(bool(rows)); self.empty.setVisible(not rows)

    def refresh(self):
        self.exp.setVisible(self.ctx.can("reports.export"))
        kind = self.kind.currentData()
        d0, d1 = self.range.range()
        t0, t1 = range_bounds(d0, d1)
        r = self.ctx.reports
        self.chart_card.setVisible(kind in ("summary", "categories", "top"))
        self.note.setText("")
        if kind == "summary":
            s = r.summary(d0, d1)
            self._kpi([("Net sales", fmt(s["net"])), ("Transactions", f"{s['transactions']:,}"),
                       ("Avg transaction", fmt(s["atv"])), ("Linked to a customer", f"{s['linked_pct']:.0f}%")])
            daily = r.daily_totals(d0, d1) if (d1 - d0).days <= 92 else []
            self.chart_card.layout().itemAt(0).widget().setText("Net sales per day" if daily else "Net sales per month")
            mon = r.monthly_totals(d0, d1)
            if daily:
                self.chart.set_data([dt.date.fromisoformat(k).strftime("%d %b") for k, _ in daily], [max(0, v) for _, v in daily])
            else:
                self.chart.set_data([m["month"] for m in mon], [max(0, m["net"]) for m in mon])
            self._table([("month", "Month"), ("transactions", "Transactions"), ("gross", "Gross sales"),
                         ("refunds", "Refunds"), ("net", "Net sales")], mon, {"gross", "refunds", "net"})
            self.note.setText(f"Refunds are counted on the day they were given. Voided sales in this period: {s['voided']}.")
        elif kind in ("products", "top"):
            rows = r.by_product(t0, t1, 15 if kind == "top" else 5000)
            self._kpi([("Products sold", f"{len(rows):,}"), ("Units", f"{sum(x['units'] or 0 for x in rows):,}"),
                       ("Net value", fmt(sum(x["net"] or 0 for x in rows)))])
            self.chart_card.layout().itemAt(0).widget().setText("Units sold (top 15)")
            self.chart.money = False
            self.chart.set_data([x["name"][:14] for x in rows[:15]], [x["units"] or 0 for x in rows[:15]])
            self._table([("sku", "SKU"), ("name", "Product"), ("category", "Category"), ("units", "Units"),
                         ("net", "Net value")], rows, {"net"})
        elif kind == "categories":
            rows = r.by_category(t0, t1)
            self._kpi([("Categories", str(len(rows))), ("Net value", fmt(sum(x["net"] or 0 for x in rows)))])
            self.chart_card.layout().itemAt(0).widget().setText("Net sales by category")
            self.chart.money = True
            self.chart.set_data([x["category"] for x in rows], [max(0, x["net"] or 0) for x in rows])
            self._table([("category", "Category"), ("units", "Units"), ("net", "Net value")], rows, {"net"})
        elif kind == "repeat":
            rows = r.repeat_customers(t0, t1)
            self._kpi([("Repeat customers", str(len(rows))), ("Their purchases", str(sum(x["visits"] for x in rows))),
                       ("Their spending", fmt(sum(x["gross"] or 0 for x in rows)))])
            self._table([("full_name", "Customer"), ("loyalty_id", "Loyalty ID"), ("tier", "Tier"), ("visits", "Purchases"),
                         ("gross", "Spent"), ("last", "Last purchase")], rows, {"gross"}, {"last"})
        elif kind == "vip":
            rows = r.vip_customers()
            self._kpi([("Customers with a tier", str(len(rows))),
                       ("Their net spending", fmt(sum(x["net"] or 0 for x in rows)))])
            self._table([("full_name", "Customer"), ("loyalty_id", "Loyalty ID"), ("tier", "Tier"), ("net", "Net spending"),
                         ("last", "Last purchase"), ("vip_reason", "Why")], rows, {"net"}, {"last"})
            self.note.setText("Current tiers (not limited to the date range).")
        elif kind == "clv":
            rows = r.lifetime_values()
            for x in rows:
                x["net"] = (x["gross"] or 0) - (x["refunds"] or 0)
                x["atv"] = (x["gross"] or 0) // max(1, x["transactions"])
            self._kpi([("Customers who bought", str(len(rows))),
                       ("Average lifetime value", fmt(sum(x["net"] for x in rows) // max(1, len(rows))))])
            self._table([("full_name", "Customer"), ("loyalty_id", "Loyalty ID"), ("transactions", "Purchases"),
                         ("gross", "Gross"), ("refunds", "Refunds"), ("net", "Net (lifetime)"), ("atv", "Avg purchase"),
                         ("first", "First purchase"), ("last", "Last purchase")], rows,
                        {"gross", "refunds", "net", "atv"}, {"first", "last"})
            self.note.setText("Based on actual transactions only - no predictions.")
        elif kind == "refunds":
            rows = r.refunds(t0, t1)
            self._kpi([("Refunds", str(len(rows))), ("Amount refunded", fmt(sum(x["amount"] for x in rows)))])
            self._table([("refund_no", "Refund"), ("refunded_at", "Date"), ("receipt_no", "Receipt"), ("customer", "Customer"),
                         ("amount", "Amount"), ("reason", "Reason"), ("staff", "Staff")], rows, {"amount"}, {"refunded_at"})
        else:
            x = r.retention(d0, d1)
            self._kpi([("Retention rate", f"{x['rate']:.0f}%"), ("Bought before & again", str(x["retained"])),
                       ("Bought in previous period", str(x["previous"])), ("New buyers", str(x["new"]))])
            self._table([("k", "Measure"), ("v", "Value")],
                        [{"k": "Customers who bought in the previous period of equal length", "v": x["previous"]},
                         {"k": "Customers who bought in this period", "v": x["current"]},
                         {"k": "Bought in both (retained)", "v": x["retained"]},
                         {"k": "First-time buyers in this period", "v": x["new"]}])
            self.note.setText("Retention compares this period with the previous period of the same length.")
        if kind not in ("products", "top"):
            self.chart.money = True

    def export(self):
        if not self.rows:
            info(self, "Export", "Nothing to export for this period."); return
        kind = self.kind.currentData()
        d0, d1 = self.range.range()
        p, _ = QFileDialog.getSaveFileName(self, "Export report", str(exports_dir() / f"{kind}_{d0}_{d1}.csv"), "CSV (*.csv)")
        if not p:
            return
        rows = []
        for r in self.rows:
            rows.append({k: (fmt(v, symbol=False) if isinstance(v, int) and k in ("gross", "refunds", "net", "amount", "atv")
                             else v) for k, v in r.items()})
        if guarded(self, "Export", self.ctx.reports.export_csv, rows, self.cols, p, kind)[0]:
            info(self, "Export", "Report exported.")

"""Dashboard: today's KPIs, dispatch per product, mismatches, timings, busiest hours."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from nomload import theme
from nomload.i18n import _
from nomload.ui.widgets import BarChart, Card, KpiCard, PageHeader, button


class DashboardPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.setObjectName("Page")
        self.main = main
        self.app = main.app
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(sc)
        host = QWidget()
        host.setObjectName("Page")
        sc.setWidget(host)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        hdr = PageHeader("Dashboard")
        rb = hdr.add(button("Refresh"))
        rb.clicked.connect(self.refresh)
        lay.addWidget(hdr)
        k = QGridLayout()
        k.setSpacing(14)
        self.kpi_grid = k
        self.k_trucks = KpiCard("Trucks loaded today")
        self.k_units = KpiCard("Units dispatched today")
        self.k_mism = KpiCard("Mismatches today")
        self.k_avg = KpiCard("Avg loading time")
        self.k_active = KpiCard("Loading now")
        self.kpis = [self.k_trucks, self.k_units, self.k_mism, self.k_avg, self.k_active]
        lay.addLayout(k)
        g = QGridLayout()
        g.setSpacing(14)
        c1 = Card("Units dispatched per product (today)")
        self.ch_products = BarChart(integer=True)
        c1.lay.addWidget(self.ch_products)
        c2 = Card("Trucks per day (last 14 days)")
        self.ch_days = BarChart(stacked_colors=[theme.c("chart_soft"), theme.c("danger")], integer=True)
        legend = QLabel(f"<span style='color:{theme.c('chart_soft')}'>■</span> {_('cleared')} &nbsp; "
                        f"<span style='color:{theme.c('danger')}'>■</span> {_('mismatch')}")
        legend.setObjectName("Muted")
        c2.lay.addWidget(self.ch_days)
        c2.lay.addWidget(legend)
        c3 = Card("Average loading time per bay (minutes, 7 days)")
        self.ch_bays = BarChart()
        c3.lay.addWidget(self.ch_bays)
        c4 = Card("Busiest hours (trucks started, 7 days)")
        self.ch_hours = BarChart(integer=True)
        c4.lay.addWidget(self.ch_hours)
        self.chart_grid = g
        self.chart_cards = [c1, c2, c3, c4]
        self._chart_cols = 0
        self._reflow()
        lay.addLayout(g)
        self.ins = Card("Insights")
        self.ins_lbl = QLabel()
        self.ins_lbl.setWordWrap(True)
        self.ins.lay.addWidget(self.ins_lbl)
        lay.addWidget(self.ins)
        lay.addStretch(1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)

    def _reflow(self):
        """2x2 charts and 5 KPI tiles in a row on wide screens; stacked on narrow ones."""
        w = self.width() or 1400
        cols = 2 if w >= 1000 else 1
        kcols = 5 if w >= 1000 else 3
        if (cols, kcols) == self._chart_cols:
            return
        self._chart_cols = (cols, kcols)
        for c in self.chart_cards:
            self.chart_grid.removeWidget(c)
        for i, c in enumerate(self.chart_cards):
            self.chart_grid.addWidget(c, i // cols, i % cols)
        if hasattr(self, "kpis"):
            for c in self.kpis:
                self.kpi_grid.removeWidget(c)
            for i, c in enumerate(self.kpis):
                self.kpi_grid.addWidget(c, i // kcols, i % kcols)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reflow()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def refresh(self):
        st = self.app.stats
        t = st.today()
        self.k_trucks.set(t["trucks"])
        self.k_units.set(f"{t['units_total']:,}")
        self.k_mism.set(t["mismatches"], theme.c("danger") if t["mismatches"] else None)
        a = t["avg_load_s"]
        self.k_avg.set("-" if not a else (f"{a:.0f} s" if a < 60 else f"{a / 60:.0f} min"))
        self.k_active.set(t["active"])
        names = [n for n, _v in t["units_by_product"]]
        self.ch_products.set_data(names, [v for _n, v in t["units_by_product"]])
        days = st.trucks_per_day(14)
        self.ch_days.set_data([d for d, *_ in days], [ok for _d, ok, _b in days], [b for _d, _o, b in days])
        bays = st.avg_time_per_bay(7)
        self.ch_bays.set_data([b for b, _ in bays], [v for _b, v in bays])
        hrs = st.busiest_hours(7)
        first = next((i for i, v in enumerate(hrs) if v), 6)
        last = 23 - next((i for i, v in enumerate(reversed(hrs)) if v), 3)
        lo, hi = min(first, 6), max(last, 20)
        self.ch_hours.set_data([f"{h:02d}" for h in range(lo, hi + 1)], hrs[lo:hi + 1])
        self.ins_lbl.setText("<br>".join("• " + s for s in st.insights()))

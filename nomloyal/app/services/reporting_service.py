"""Dashboard metrics and reports - every number comes from the database.

"Valid" sales exclude voided sales; net amounts subtract refunds. Refunds are reported on the day they happen.
"""
from __future__ import annotations

import csv
import datetime as dt
import time
from pathlib import Path

from app.security.audit import audit

VALID = "s.status<>'voided'"


def day_bounds(d: dt.date) -> tuple[float, float]:
    t0 = dt.datetime.combine(d, dt.time.min).timestamp()
    return t0, t0 + 86400


def range_bounds(d0: dt.date, d1: dt.date) -> tuple[float, float]:
    return day_bounds(d0)[0], day_bounds(d1)[1]


class ReportingService:
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth

    def _sales_sum(self, t0, t1) -> int:
        return int(self.db.scalar(f"SELECT SUM(total) FROM sales s WHERE {VALID} AND sold_at>=? AND sold_at<?",
                                  (t0, t1), default=0))

    def _refund_sum(self, t0, t1) -> int:
        return int(self.db.scalar("SELECT SUM(r.amount) FROM refunds r JOIN sales s ON s.id=r.sale_id "
                                  f"WHERE {VALID} AND r.refunded_at>=? AND r.refunded_at<?", (t0, t1), default=0))

    # ------------------------------------------------------------------ dashboard
    def dashboard(self, today: dt.date | None = None) -> dict:
        self.auth.require("dashboard.view")
        today = today or dt.date.today()
        t0, t1 = day_bounds(today)
        m0 = dt.datetime(today.year, today.month, 1).timestamp()
        customers = self.db.scalar("SELECT COUNT(*) FROM customers WHERE status='active'", default=0)
        buyers = self.db.scalar(f"SELECT COUNT(DISTINCT customer_id) FROM sales s WHERE {VALID} AND customer_id IS NOT NULL",
                                default=0)
        returning = self.db.scalar(f"SELECT COUNT(*) FROM (SELECT customer_id FROM sales s WHERE {VALID} AND "
                                   "customer_id IS NOT NULL GROUP BY customer_id HAVING COUNT(DISTINCT date(sold_at, "
                                   "'unixepoch', 'localtime')) >= 2)", default=0)
        vip = self.db.scalar("SELECT COUNT(*) FROM customers WHERE status='active' AND "
                             "COALESCE(vip_override_tier, vip_tier) IS NOT NULL", default=0)
        month_n = self.db.scalar(f"SELECT COUNT(*) FROM sales s WHERE {VALID} AND sold_at>=? AND sold_at<?", (m0, t1),
                                 default=0)
        month_total = self._sales_sum(m0, t1) - self._refund_sum(m0, t1)
        out = {
            "today_sales": self._sales_sum(t0, t1) - self._refund_sum(t0, t1),
            "today_count": self.db.scalar(f"SELECT COUNT(*) FROM sales s WHERE {VALID} AND sold_at>=? AND sold_at<?",
                                          (t0, t1), default=0),
            "month_sales": month_total,
            "customers": customers, "returning": returning,
            "repeat_pct": round(100 * returning / buyers, 1) if buyers else 0.0,
            "vip": vip,
            "atv": (self._sales_sum(m0, t1) // month_n) if month_n else 0,
            "open_alerts": self.db.scalar("SELECT COUNT(*) FROM alerts WHERE status='open'", default=0),
            "has_demo": bool(self.db.scalar("SELECT 1 FROM sales WHERE is_demo=1 LIMIT 1")),
        }
        out["recent_sales"] = [dict(r) for r in self.db.q(
            "SELECT s.id, s.receipt_no, s.sold_at, s.total, s.status, s.is_demo, c.full_name customer FROM sales s "
            "LEFT JOIN customers c ON c.id=s.customer_id ORDER BY s.sold_at DESC LIMIT 8")]
        out["recent_activity"] = [dict(r) for r in self.db.q(
            "SELECT v.visited_at, v.method, c.full_name customer, c.id customer_id, "
            "COALESCE(c.vip_override_tier, c.vip_tier) tier FROM customer_visits v JOIN customers c ON c.id=v.customer_id "
            "WHERE c.status='active' ORDER BY v.visited_at DESC LIMIT 8")]
        out["recent_refunds"] = [dict(r) for r in self.db.q(
            "SELECT r.refund_no, r.refunded_at, r.amount, r.reason, s.receipt_no FROM refunds r JOIN sales s "
            "ON s.id=r.sale_id ORDER BY r.refunded_at DESC LIMIT 6")]
        out["trend"] = self.daily_totals(today - dt.timedelta(days=13), today)
        out["top_categories"] = self.by_category(*range_bounds(today - dt.timedelta(days=29), today))[:6]
        return out

    # ------------------------------------------------------------------ building blocks
    def daily_totals(self, d0: dt.date, d1: dt.date) -> list[tuple[str, int]]:
        t0, t1 = range_bounds(d0, d1)
        sales = {r[0]: r[1] for r in self.db.q(
            f"SELECT date(sold_at,'unixepoch','localtime') d, SUM(total) FROM sales s WHERE {VALID} AND sold_at>=? "
            "AND sold_at<? GROUP BY d", (t0, t1))}
        refunds = {r[0]: r[1] for r in self.db.q(
            "SELECT date(r.refunded_at,'unixepoch','localtime') d, SUM(r.amount) FROM refunds r JOIN sales s "
            f"ON s.id=r.sale_id WHERE {VALID} AND r.refunded_at>=? AND r.refunded_at<? GROUP BY d", (t0, t1))}
        out, d = [], d0
        while d <= d1:
            k = d.isoformat()
            out.append((k, int(sales.get(k, 0) or 0) - int(refunds.get(k, 0) or 0)))
            d += dt.timedelta(days=1)
        return out

    def monthly_totals(self, d0: dt.date, d1: dt.date) -> list[dict]:
        t0, t1 = range_bounds(d0, d1)
        rows = {r["m"]: dict(r) for r in self.db.q(
            f"SELECT strftime('%Y-%m', sold_at,'unixepoch','localtime') m, COUNT(*) n, SUM(total) gross FROM sales s "
            f"WHERE {VALID} AND sold_at>=? AND sold_at<? GROUP BY m", (t0, t1))}
        refunds = {r[0]: r[1] for r in self.db.q(
            "SELECT strftime('%Y-%m', r.refunded_at,'unixepoch','localtime') m, SUM(r.amount) FROM refunds r "
            f"JOIN sales s ON s.id=r.sale_id WHERE {VALID} AND r.refunded_at>=? AND r.refunded_at<? GROUP BY m", (t0, t1))}
        out = []
        for m in sorted(set(rows) | set(refunds)):
            r = rows.get(m, {"n": 0, "gross": 0})
            ref = int(refunds.get(m, 0) or 0)
            out.append({"month": m, "transactions": r["n"] or 0, "gross": int(r["gross"] or 0), "refunds": ref,
                        "net": int(r["gross"] or 0) - ref})
        return out

    def by_category(self, t0: float, t1: float) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT i.category, SUM(i.qty - i.refunded_qty) units, "
            "SUM(i.line_total - (i.line_total * i.refunded_qty) / i.qty) net FROM sale_items i JOIN sales s "
            f"ON s.id=i.sale_id WHERE {VALID} AND s.sold_at>=? AND s.sold_at<? GROUP BY i.category ORDER BY net DESC",
            (t0, t1))]

    def by_product(self, t0: float, t1: float, limit: int = 1000) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT i.sku, i.name, i.category, SUM(i.qty - i.refunded_qty) units, "
            "SUM(i.line_total - (i.line_total * i.refunded_qty) / i.qty) net FROM sale_items i JOIN sales s "
            f"ON s.id=i.sale_id WHERE {VALID} AND s.sold_at>=? AND s.sold_at<? GROUP BY i.sku, i.name, i.category "
            "ORDER BY units DESC, net DESC LIMIT ?", (t0, t1, limit))]

    # ------------------------------------------------------------------ customer analytics
    def customer_stats(self, cid: int) -> dict:
        net = self.db.scalar("SELECT SUM(s.total - COALESCE((SELECT SUM(amount) FROM refunds r WHERE r.sale_id=s.id),0)) "
                             f"FROM sales s WHERE s.customer_id=? AND {VALID}", (cid,), default=0)
        n = self.db.scalar(f"SELECT COUNT(*) FROM sales s WHERE s.customer_id=? AND {VALID}", (cid,), default=0)
        gross = self.db.scalar(f"SELECT SUM(total) FROM sales s WHERE s.customer_id=? AND {VALID}", (cid,), default=0)
        refunds = self.db.scalar(f"SELECT SUM(r.amount) FROM refunds r JOIN sales s ON s.id=r.sale_id "
                                 f"WHERE s.customer_id=? AND {VALID}", (cid,), default=0)
        cats = [r[0] for r in self.db.q(
            "SELECT i.category FROM sale_items i JOIN sales s ON s.id=i.sale_id "
            f"WHERE s.customer_id=? AND {VALID} GROUP BY i.category ORDER BY SUM(i.qty-i.refunded_qty) DESC LIMIT 3", (cid,))]
        return {"net": int(net), "gross": int(gross), "refunds": int(refunds), "transactions": n,
                "atv": int(gross) // n if n else 0,
                "last_purchase": self.db.scalar(f"SELECT MAX(sold_at) FROM sales s WHERE s.customer_id=? AND {VALID}", (cid,)),
                "first_purchase": self.db.scalar(f"SELECT MIN(sold_at) FROM sales s WHERE s.customer_id=? AND {VALID}",
                                                 (cid,)),
                "last_visit": self.db.scalar("SELECT MAX(visited_at) FROM customer_visits WHERE customer_id=?", (cid,)),
                "visits": self.db.scalar("SELECT COUNT(*) FROM customer_visits WHERE customer_id=?", (cid,), default=0),
                "favorite_categories": cats}

    def timeline(self, cid: int) -> list[dict]:
        """Purchases, refunds and visits of one customer, newest first."""
        out = []
        for s in self.db.q("SELECT id, receipt_no, sold_at, total, status FROM sales WHERE customer_id=?", (cid,)):
            items = ", ".join(f"{r['qty']} x {r['name']}" for r in self.db.q(
                "SELECT qty, name FROM sale_items WHERE sale_id=? ORDER BY id", (s["id"],)))
            out.append({"ts": s["sold_at"], "kind": "purchase", "ref": s["receipt_no"], "amount": s["total"],
                        "status": s["status"], "detail": items, "sale_id": s["id"]})
        for r in self.db.q("SELECT r.refund_no, r.refunded_at, r.amount, r.reason, s.id sale_id FROM refunds r JOIN sales s "
                           "ON s.id=r.sale_id WHERE s.customer_id=?", (cid,)):
            out.append({"ts": r["refunded_at"], "kind": "refund", "ref": r["refund_no"], "amount": -r["amount"],
                        "status": "", "detail": r["reason"], "sale_id": r["sale_id"]})
        for v in self.db.q("SELECT visited_at, method FROM customer_visits WHERE customer_id=? AND method<>'purchase'", (cid,)):
            out.append({"ts": v["visited_at"], "kind": "visit", "ref": "", "amount": None, "status": "",
                        "detail": f"Checked in by {v['method'].replace('_', ' ')}", "sale_id": None})
        return sorted(out, key=lambda x: x["ts"], reverse=True)

    def repeat_customers(self, t0: float, t1: float) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT c.id, c.loyalty_id, c.full_name, COALESCE(c.vip_override_tier, c.vip_tier) tier, COUNT(*) visits, "
            "SUM(s.total) gross, MAX(s.sold_at) last FROM sales s JOIN customers c ON c.id=s.customer_id "
            f"WHERE {VALID} AND s.sold_at>=? AND s.sold_at<? GROUP BY c.id HAVING COUNT(*)>=2 ORDER BY visits DESC, gross DESC",
            (t0, t1))]

    def vip_customers(self) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT c.id, c.loyalty_id, c.full_name, COALESCE(c.vip_override_tier, c.vip_tier) tier, "
            "c.vip_override_tier IS NOT NULL overridden, c.vip_reason, c.vip_override_reason, t.rank, "
            "(SELECT SUM(s.total - COALESCE((SELECT SUM(amount) FROM refunds r WHERE r.sale_id=s.id),0)) FROM sales s "
            f"WHERE s.customer_id=c.id AND {VALID}) net, (SELECT MAX(sold_at) FROM sales s WHERE s.customer_id=c.id AND {VALID}) last "
            "FROM customers c LEFT JOIN vip_tiers t ON t.name=COALESCE(c.vip_override_tier, c.vip_tier) "
            "WHERE c.status='active' AND COALESCE(c.vip_override_tier, c.vip_tier) IS NOT NULL "
            "ORDER BY t.rank DESC, net DESC")]

    def lifetime_values(self, limit: int = 1000) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT c.id, c.loyalty_id, c.full_name, COUNT(s.id) transactions, SUM(s.total) gross, "
            "SUM(COALESCE((SELECT SUM(amount) FROM refunds r WHERE r.sale_id=s.id),0)) refunds, "
            "MIN(s.sold_at) first, MAX(s.sold_at) last FROM customers c JOIN sales s ON s.customer_id=c.id "
            f"WHERE {VALID} AND c.status<>'anonymized' GROUP BY c.id ORDER BY gross DESC LIMIT ?", (limit,))]

    def refunds(self, t0: float, t1: float) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT r.refund_no, r.refunded_at, s.receipt_no, c.full_name customer, r.amount, r.reason, u.username staff "
            "FROM refunds r JOIN sales s ON s.id=r.sale_id LEFT JOIN customers c ON c.id=s.customer_id "
            "LEFT JOIN staff_users u ON u.id=r.processed_by WHERE r.refunded_at>=? AND r.refunded_at<? "
            "ORDER BY r.refunded_at DESC", (t0, t1))]

    def retention(self, d0: dt.date, d1: dt.date) -> dict:
        """Of the customers who bought in the previous period of equal length, how many bought again in this one."""
        t0, t1 = range_bounds(d0, d1)
        span = t1 - t0
        prev = {r[0] for r in self.db.q(f"SELECT DISTINCT customer_id FROM sales s WHERE {VALID} AND customer_id IS NOT NULL "
                                        "AND sold_at>=? AND sold_at<?", (t0 - span, t0))}
        cur = {r[0] for r in self.db.q(f"SELECT DISTINCT customer_id FROM sales s WHERE {VALID} AND customer_id IS NOT NULL "
                                       "AND sold_at>=? AND sold_at<?", (t0, t1))}
        kept = prev & cur
        return {"previous": len(prev), "current": len(cur), "retained": len(kept), "new": len(cur - prev),
                "rate": round(100 * len(kept) / len(prev), 1) if prev else 0.0}

    def summary(self, d0: dt.date, d1: dt.date) -> dict:
        t0, t1 = range_bounds(d0, d1)
        n = self.db.scalar(f"SELECT COUNT(*) FROM sales s WHERE {VALID} AND sold_at>=? AND sold_at<?", (t0, t1), default=0)
        gross = self._sales_sum(t0, t1)
        ref = self._refund_sum(t0, t1)
        linked = self.db.scalar(f"SELECT COUNT(*) FROM sales s WHERE {VALID} AND sold_at>=? AND sold_at<? "
                                "AND customer_id IS NOT NULL", (t0, t1), default=0)
        return {"transactions": n, "gross": gross, "refunds": ref, "net": gross - ref, "atv": gross // n if n else 0,
                "linked_pct": round(100 * linked / n, 1) if n else 0.0,
                "voided": self.db.scalar("SELECT COUNT(*) FROM sales WHERE status='voided' AND sold_at>=? AND sold_at<?",
                                         (t0, t1), default=0)}

    # ------------------------------------------------------------------ export
    def export_csv(self, rows: list[dict], columns: list[tuple[str, str]], path: str | Path, report: str) -> Path:
        user = self.auth.require("reports.export")
        path = Path(path)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([h for _k, h in columns])
            for r in rows:
                w.writerow([_cell(r.get(k)) for k, _h in columns])
        audit(self.db, user, "report_exported", "report", report, {"rows": len(rows), "file": path.name})
        return path


def _cell(v):
    if isinstance(v, float) and v > 1e9:            # timestamps
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(v))
    return "" if v is None else v

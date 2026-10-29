"""VIP / tier engine. Eligibility comes ONLY from valid sales records:

* voided sales are ignored
* refunds are subtracted from the sale they belong to ("net" amounts)
* a tier is reached by EITHER a single net purchase >= its single-purchase threshold OR net spending in the
  tier's rolling window (months) >= its spending threshold
* the customer gets the highest tier reached; a manual override (audited, with reason) takes precedence
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field

from app.models import VipTier
from app.money import fmt
from app.security.audit import audit
from app.services.errors import NotFound, ValidationError


@dataclass
class Eligibility:
    tier: str | None
    reasons: list[str] = field(default_factory=list)
    qualifying_sales: list[dict] = field(default_factory=list)
    net_window: dict[str, int] = field(default_factory=dict)      # tier -> net spending in its window
    best_single: dict[str, int] = field(default_factory=dict)     # tier -> best single net purchase in window


def months_ago(months: int, now: float | None = None) -> float:
    d = dt.datetime.fromtimestamp(now or time.time())
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12; y -= 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31,
                      30, 31][m - 1])
    return d.replace(year=y, month=m, day=day).timestamp()


class VipService:
    def __init__(self, db, auth, settings):
        self.db = db
        self.auth = auth
        self.settings = settings

    # ------------------------------------------------------------------ tiers
    def tiers(self, active_only: bool = False) -> list[VipTier]:
        rows = self.db.q("SELECT * FROM vip_tiers" + (" WHERE active=1" if active_only else "") + " ORDER BY rank")
        return [VipTier(r["id"], r["name"], r["rank"], r["min_single_purchase"], r["min_rolling_spend"],
                        r["window_months"], r["color"], bool(r["active"])) for r in rows]

    def tier_color(self, name: str | None) -> str:
        for t in self.tiers():
            if t.name == name:
                return t.color
        return "#64748B"

    def save_tier(self, name: str, rank: int, min_single: int | None, min_rolling: int | None, window_months: int = 12,
                  color: str = "#0E7C7B", active: bool = True, tid: int | None = None) -> int:
        user = self.auth.require("vip.rules")
        name = (name or "").strip()
        if not name or len(name) > 30:
            raise ValidationError("Tier name is required (max 30 characters).")
        if min_single is None and min_rolling is None:
            raise ValidationError("Set a single-purchase threshold, a spending threshold, or both.")
        for v in (min_single, min_rolling):
            if v is not None and v <= 0:
                raise ValidationError("Thresholds must be above zero.")
        if not 1 <= int(window_months) <= 120:
            raise ValidationError("The spending window must be 1 to 120 months.")
        now = time.time()
        dup = self.db.one("SELECT id FROM vip_tiers WHERE name=?", (name,))
        if dup and dup["id"] != tid:
            raise ValidationError("A tier with this name already exists.")
        if tid:
            old = self.db.one("SELECT name FROM vip_tiers WHERE id=?", (tid,))
            self.db.execute("UPDATE vip_tiers SET name=?, rank=?, min_single_purchase=?, min_rolling_spend=?, "
                            "window_months=?, color=?, active=?, updated_at=? WHERE id=?",
                            (name, int(rank), min_single, min_rolling, int(window_months), color, int(active), now, tid))
            if old and old["name"] != name:     # keep customers' current tiers pointing at the renamed tier
                self.db.execute("UPDATE customers SET vip_tier=? WHERE vip_tier=?", (name, old["name"]))
                self.db.execute("UPDATE customers SET vip_override_tier=? WHERE vip_override_tier=?", (name, old["name"]))
        else:
            tid = self.db.execute("INSERT INTO vip_tiers(name, rank, min_single_purchase, min_rolling_spend, window_months, "
                                  "color, active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                  (name, int(rank), min_single, min_rolling, int(window_months), color, int(active), now, now))
        audit(self.db, user, "vip_rule_saved", "vip_tier", tid, {"name": name, "rank": rank, "single": min_single,
                                                                  "rolling": min_rolling, "months": window_months,
                                                                  "active": active})
        self.recalculate_all(reason="rules changed")
        return tid

    def delete_tier(self, tid: int):
        user = self.auth.require("vip.rules")
        r = self.db.one("SELECT name FROM vip_tiers WHERE id=?", (tid,))
        if r is None:
            raise NotFound("Tier not found.")
        if self.db.scalar("SELECT COUNT(*) FROM customers WHERE vip_override_tier=?", (r["name"],)):
            raise ValidationError("Some customers have a manual override to this tier. Remove the overrides first.")
        self.db.execute("DELETE FROM vip_tiers WHERE id=?", (tid,))
        audit(self.db, user, "vip_rule_deleted", "vip_tier", tid, {"name": r["name"]})
        self.recalculate_all(reason="rules changed")

    # ------------------------------------------------------------------ evaluation
    def _net_sales(self, cid: int, since: float) -> list[dict]:
        return [dict(r) for r in self.db.q(
            "SELECT s.id, s.receipt_no, s.sold_at, s.total, "
            "s.total - COALESCE((SELECT SUM(amount) FROM refunds r WHERE r.sale_id=s.id), 0) AS net "
            "FROM sales s WHERE s.customer_id=? AND s.status<>'voided' AND s.sold_at>=? ORDER BY s.sold_at",
            (cid, since))]

    def evaluate(self, cid: int, now: float | None = None) -> Eligibility:
        now = now or time.time()
        best: Eligibility = Eligibility(None)
        for t in sorted(self.tiers(active_only=True), key=lambda t: t.rank, reverse=True):
            sales = self._net_sales(cid, months_ago(t.window_months, now))
            net = sum(s["net"] for s in sales)
            top = max((s["net"] for s in sales), default=0)
            best.net_window[t.name] = net
            best.best_single[t.name] = top
            if best.tier:
                continue
            reasons, qual = [], []
            if t.min_single_purchase is not None and top >= t.min_single_purchase:
                s = max(sales, key=lambda s: s["net"])
                reasons.append(f"Single purchase of {fmt(s['net'])} on "
                               f"{dt.datetime.fromtimestamp(s['sold_at']).strftime('%d %b %Y')} ({s['receipt_no']}) "
                               f"reaches the {t.name} threshold of {fmt(t.min_single_purchase)}.")
                qual.append(s)
            if t.min_rolling_spend is not None and net >= t.min_rolling_spend:
                reasons.append(f"Net spending of {fmt(net)} in the last {t.window_months} months reaches the "
                               f"{t.name} threshold of {fmt(t.min_rolling_spend)}.")
                qual = sales
            if reasons:
                best.tier, best.reasons, best.qualifying_sales = t.name, reasons, qual
        if not best.tier:
            best.reasons = ["No tier threshold is reached by the customer's valid purchases."]
        return best

    def recalculate(self, cid: int, reason: str = "") -> str | None:
        r = self.db.one("SELECT vip_tier, status FROM customers WHERE id=?", (cid,))
        if r is None:
            return None
        e = self.evaluate(cid)
        if r["status"] == "anonymized":
            e = Eligibility(None, ["Customer data deleted."])
        self.db.execute("UPDATE customers SET vip_tier=?, vip_reason=?, vip_updated_at=? WHERE id=?",
                        (e.tier, " ".join(e.reasons), time.time(), cid))
        if e.tier != r["vip_tier"]:
            audit(self.db, self.auth.user, "vip_tier_changed", "customer", cid,
                  {"from": r["vip_tier"], "to": e.tier, "because": reason})
        return e.tier

    def recalculate_all(self, reason: str = "") -> int:
        n = 0
        for r in self.db.q("SELECT id FROM customers WHERE status<>'anonymized'"):
            self.recalculate(r["id"], reason)
            n += 1
        return n

    # ------------------------------------------------------------------ manual override
    def override(self, cid: int, tier: str | None, reason: str):
        user = self.auth.require("vip.override")
        if not reason.strip():
            raise ValidationError("A reason is required for a manual VIP change.")
        if tier is not None and tier not in [t.name for t in self.tiers()]:
            raise ValidationError("Unknown tier.")
        now = time.time()
        self.db.execute("UPDATE customers SET vip_override_tier=?, vip_override_reason=?, vip_override_by=?, "
                        "vip_override_at=?, updated_at=? WHERE id=?",
                        (tier, reason.strip() if tier else "", user.id or None, now if tier else None, now, cid))
        audit(self.db, user, "vip_override_set" if tier else "vip_override_removed", "customer", cid,
              {"tier": tier, "reason": reason.strip()})

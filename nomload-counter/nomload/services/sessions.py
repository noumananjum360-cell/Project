"""Loading sessions: counting attribution, matching against gate passes,
tolerance rules, supervisor review/release and soft delete."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from nomload.data.db import Database
from nomload.services.catalog import GatePass, GatePassService, Product, ProductService
from nomload.services.context import Settings, User, audit

COUNTED_REVIEWS = ("auto", "accepted", "manual")


@dataclass
class ProductLine:
    product_id: int
    name: str
    expected: int | None       # None when there is no gate pass
    counted: int
    pending: int               # flagged counts waiting for review (not included in counted)
    allowed: int = 0

    @property
    def diff(self) -> int:
        return self.counted - (self.expected or 0)

    @property
    def ok(self) -> bool:
        return self.expected is not None and abs(self.diff) <= self.allowed

    def to_dict(self) -> dict:
        return {"product_id": self.product_id, "name": self.name, "expected": self.expected, "counted": self.counted,
                "pending": self.pending, "allowed": self.allowed, "diff": self.diff, "ok": self.ok}


@dataclass
class SessionSummary:
    id: int
    bay_id: int
    bay_name: str
    status: str
    started_at: float
    ended_at: float | None
    plate_text: str
    plate_confidence: float | None
    plate_image: str | None
    gate_pass: GatePass | None
    lines: list[ProductLine] = field(default_factory=list)
    started_by: str = ""
    closed_by: str = ""
    released_by: str = ""
    release_reason: str = ""
    clip_path: str | None = None
    auto_started: bool = False
    notes: str = ""

    @property
    def total_counted(self) -> int:
        return sum(l.counted for l in self.lines)

    @property
    def total_expected(self) -> int:
        return sum(l.expected or 0 for l in self.lines)

    @property
    def total_pending(self) -> int:
        return sum(l.pending for l in self.lines)

    @property
    def duration_s(self) -> float:
        return (self.ended_at or time.time()) - self.started_at

    @property
    def matched(self) -> bool:
        return bool(self.lines) and all(l.ok for l in self.lines)


class SessionError(Exception):
    pass


class SessionService:
    def __init__(self, db: Database, settings: Settings, products: ProductService, gate_passes: GatePassService):
        self.db = db
        self.settings = settings
        self.products = products
        self.gate_passes = gate_passes

    # ------------------------------------------------------------- lifecycle
    def active_for_bay(self, bay_id: int) -> int | None:
        return self.db.scalar("SELECT id FROM sessions WHERE bay_id=? AND status='active' AND deleted=0 "
                              "ORDER BY id DESC LIMIT 1", (bay_id,))

    def start(self, bay_id: int, user: User | None, gate_pass_id: int | None = None, auto: bool = False) -> int:
        if self.active_for_bay(bay_id):
            raise SessionError("A loading session is already running on this bay.")
        if gate_pass_id:
            gp = self.gate_passes.get(gate_pass_id)
            if gp is None or gp.status not in ("open",):
                raise SessionError("This gate pass is not open (already loading, completed or cancelled).")
        sid = self.db.execute("INSERT INTO sessions(bay_id, gate_pass_id, status, started_at, started_by, auto_started) "
                              "VALUES (?,?,?,?,?,?)", (bay_id, gate_pass_id, "active", time.time(),
                                                       user.id if user and user.id else None, int(auto)))
        if gate_pass_id:
            self.gate_passes.set_status(gate_pass_id, "loading", user)
        audit(self.db, user, "session_started", "session", sid, {"bay": bay_id, "gate_pass": gate_pass_id, "auto": auto})
        return sid

    def link_gate_pass(self, sid: int, gate_pass_id: int, user: User):
        r = self.db.one("SELECT gate_pass_id, status FROM sessions WHERE id=?", (sid,))
        if r is None or r["status"] != "active":
            raise SessionError("Session is not active.")
        gp = self.gate_passes.get(gate_pass_id)
        if gp is None or gp.status != "open":
            raise SessionError("Gate pass is not open.")
        if r["gate_pass_id"]:
            self.gate_passes.set_status(r["gate_pass_id"], "open", user)
        self.db.execute("UPDATE sessions SET gate_pass_id=? WHERE id=?", (gate_pass_id, sid))
        self.gate_passes.set_status(gate_pass_id, "loading", user)
        # re-attribute events of classes that map uniquely to a gate pass product
        self._reattribute(sid)
        audit(self.db, user, "session_gate_pass_linked", "session", sid, {"gate_pass": gp.number})

    def set_plate(self, sid: int, text: str, confidence: float | None, image_path: str | None = None,
                  user: User | None = None, corrected: bool = False):
        self.db.execute("UPDATE sessions SET plate_text=?, plate_confidence=?, plate_image=COALESCE(?, plate_image), "
                        "plate_corrected_by=? WHERE id=?",
                        (text, confidence, image_path, user.id if corrected and user else None, sid))
        audit(self.db, user, "plate_corrected" if corrected else "plate_read", "session", sid,
              {"plate": text, "confidence": confidence})

    # ------------------------------------------------------------- counting
    def resolve_product(self, sid: int, cls: str, active_product_id: int | None = None) -> Product | None:
        r = self.db.one("SELECT gate_pass_id FROM sessions WHERE id=?", (sid,))
        candidates = []
        if r and r["gate_pass_id"]:
            gp = self.gate_passes.get(r["gate_pass_id"])
            for it in gp.items:
                p = self.products.get(it.product_id)
                if p and p.detector_class == cls:
                    candidates.append(p)
        if len(candidates) == 1:
            return candidates[0]
        if active_product_id:
            p = self.products.get(active_product_id)
            if p and p.detector_class == cls and (not candidates or p in candidates):
                return p
        if candidates:
            # the first line that still needs units
            lines = {l.product_id: l for l in self.lines(sid)}
            for p in candidates:
                l = lines.get(p.id)
                if l and (l.expected is None or l.counted < l.expected):
                    return p
            return candidates[0]
        for p in self.products.list(active_only=True):
            if p.detector_class == cls:
                return p
        return None

    def add_event(self, sid: int, cls: str, direction: int, confidence: float, flagged: bool, reason: str = "",
                  track_id: int | None = None, snapshot: str | None = None, box=None,
                  active_product_id: int | None = None, ts: float | None = None) -> tuple[int, Product | None]:
        p = self.resolve_product(sid, cls, active_product_id)
        units = p.units_per_detection if p else 1
        review = "pending" if flagged else "auto"
        eid = self.db.execute("INSERT INTO count_events(session_id, product_id, cls, direction, units, confidence, review, "
                              "reason, ts, track_id, snapshot, box) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              (sid, p.id if p else None, cls, direction, units, confidence, review, reason,
                               ts or time.time(), track_id, snapshot, json.dumps(box) if box else None))
        return eid, p

    def manual_adjust(self, sid: int, product_id: int, delta: int, supervisor: User, reason: str):
        if not supervisor.can("edit_counts"):
            raise SessionError("Only a supervisor can adjust counts.")
        if len(reason.strip()) < 4:
            raise SessionError("Please write a reason for the adjustment.")
        p = self.products.get(product_id)
        direction = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            self.db.execute("INSERT INTO count_events(session_id, product_id, cls, direction, units, confidence, review, "
                            "reason, reviewed_by, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (sid, product_id, p.detector_class if p else "manual", direction, 1, 1.0, "manual",
                             reason, supervisor.id, time.time()))
        audit(self.db, supervisor, "count_adjusted", "session", sid, {"product": product_id, "delta": delta,
                                                                     "reason": reason})

    def review_event(self, event_id: int, accept: bool, supervisor: User, product_id: int | None = None):
        if not supervisor.can("review_counts"):
            raise SessionError("Only a supervisor can review counts.")
        self.db.execute("UPDATE count_events SET review=?, reviewed_by=?, product_id=COALESCE(?, product_id) WHERE id=?",
                        ("accepted" if accept else "rejected", supervisor.id, product_id, event_id))
        sid = self.db.scalar("SELECT session_id FROM count_events WHERE id=?", (event_id,))
        audit(self.db, supervisor, "count_accepted" if accept else "count_rejected", "count_event", event_id,
              {"session": sid, "product": product_id})

    def pending_events(self, sid: int):
        return self.db.q("SELECT e.*, p.name AS product FROM count_events e LEFT JOIN products p ON p.id=e.product_id "
                         "WHERE e.session_id=? AND e.review='pending' ORDER BY e.ts", (sid,))

    def events(self, sid: int):
        return self.db.q("SELECT e.*, p.name AS product FROM count_events e LEFT JOIN products p ON p.id=e.product_id "
                         "WHERE e.session_id=? ORDER BY e.ts", (sid,))

    def _reattribute(self, sid: int):
        for e in self.db.q("SELECT id, cls FROM count_events WHERE session_id=? AND review<>'manual'", (sid,)):
            p = self.resolve_product(sid, e["cls"])
            if p:
                self.db.execute("UPDATE count_events SET product_id=?, units=? WHERE id=?",
                                (p.id, p.units_per_detection, e["id"]))

    # ------------------------------------------------------------- matching
    def allowed_tolerance(self, product: Product | None, expected: int) -> int:
        tu = product.tolerance_units if product and product.tolerance_units is not None else self.settings.get("tolerance_units")
        tp = product.tolerance_pct if product and product.tolerance_pct is not None else self.settings.get("tolerance_pct")
        return max(int(tu or 0), int(math.floor((expected or 0) * float(tp or 0) / 100.0)))

    def lines(self, sid: int) -> list[ProductLine]:
        r = self.db.one("SELECT gate_pass_id FROM sessions WHERE id=?", (sid,))
        lines: dict[int, ProductLine] = {}
        if r and r["gate_pass_id"]:
            gp = self.gate_passes.get(r["gate_pass_id"])
            for it in gp.items:
                p = self.products.get(it.product_id)
                lines[it.product_id] = ProductLine(it.product_id, it.product_name, it.expected_qty, 0, 0,
                                                   self.allowed_tolerance(p, it.expected_qty))
        for e in self.db.q("SELECT e.product_id, p.name, e.review, SUM(e.direction*e.units) AS n FROM count_events e "
                           "LEFT JOIN products p ON p.id=e.product_id WHERE e.session_id=? "
                           "GROUP BY e.product_id, e.review", (sid,)):
            pid = e["product_id"] or 0
            if pid not in lines:
                lines[pid] = ProductLine(pid, e["name"] or "Unassigned", 0 if (r and r["gate_pass_id"]) else None, 0, 0, 0)
            if e["review"] in COUNTED_REVIEWS:
                lines[pid].counted += e["n"] or 0
            elif e["review"] == "pending":
                lines[pid].pending += e["n"] or 0
        return list(lines.values())

    def close(self, sid: int, user: User | None) -> SessionSummary:
        s = self.summary(sid)
        if s.status != "active":
            raise SessionError("Session is not active.")
        lines = s.lines
        if s.gate_pass is None:
            status = "mismatch"   # nothing to compare against: supervisor must release
        else:
            status = "cleared" if lines and all(l.ok for l in lines) and s.total_pending == 0 else "mismatch"
        result = {"lines": [l.to_dict() for l in lines], "total_counted": s.total_counted,
                  "total_expected": s.total_expected, "pending": s.total_pending,
                  "no_gate_pass": s.gate_pass is None}
        self.db.execute("UPDATE sessions SET status=?, ended_at=?, closed_by=?, result=? WHERE id=?",
                        (status, time.time(), user.id if user and user.id else None, json.dumps(result), sid))
        if s.gate_pass:
            self.gate_passes.set_status(s.gate_pass.id, "completed" if status == "cleared" else "loading", user)
        audit(self.db, user, "session_closed", "session", sid, {"status": status, **result})
        return self.summary(sid)

    def release(self, sid: int, supervisor: User, reason: str) -> SessionSummary:
        if not supervisor.can("approve_mismatch"):
            raise SessionError("Supervisor approval is required.")
        if len((reason or "").strip()) < 5:
            raise SessionError("Please write the reason for releasing this truck.")
        s = self.summary(sid)
        if s.status != "mismatch":
            raise SessionError("Only mismatched sessions need release.")
        self.db.execute("UPDATE sessions SET status='released', released_by=?, release_reason=? WHERE id=?",
                        (supervisor.id, reason.strip(), sid))
        if s.gate_pass:
            self.gate_passes.set_status(s.gate_pass.id, "completed", supervisor)
        audit(self.db, supervisor, "session_released", "session", sid, {"reason": reason})
        return self.summary(sid)

    def cancel(self, sid: int, user: User, reason: str):
        s = self.summary(sid)
        if s.status != "active":
            raise SessionError("Only an active session can be cancelled.")
        self.db.execute("UPDATE sessions SET status='cancelled', ended_at=?, closed_by=?, notes=? WHERE id=?",
                        (time.time(), user.id or None, reason, sid))
        if s.gate_pass:
            self.gate_passes.set_status(s.gate_pass.id, "open", user)
        audit(self.db, user, "session_cancelled", "session", sid, {"reason": reason})

    def soft_delete(self, sid: int, admin: User, reason: str):
        if not admin.can("delete_records"):
            raise SessionError("Only an Admin can delete records.")
        if self.db.scalar("SELECT status FROM sessions WHERE id=?", (sid,)) == "active":
            raise SessionError("This truck is still loading. Close or cancel the session first.")
        self.db.execute("UPDATE sessions SET deleted=1, notes=notes || ? WHERE id=?", (f"\n[deleted] {reason}", sid))
        audit(self.db, admin, "session_deleted", "session", sid, {"reason": reason})

    def set_clip(self, sid: int, path: str):
        self.db.execute("UPDATE sessions SET clip_path=? WHERE id=?", (path, sid))

    # ------------------------------------------------------------- read
    def summary(self, sid: int) -> SessionSummary:
        r = self.db.one("SELECT s.*, b.name AS bay_name, u1.full_name AS sb, u1.username AS sbu, u2.full_name AS cb, "
                        "u2.username AS cbu, u3.full_name AS rb, u3.username AS rbu FROM sessions s "
                        "JOIN bays b ON b.id=s.bay_id LEFT JOIN users u1 ON u1.id=s.started_by "
                        "LEFT JOIN users u2 ON u2.id=s.closed_by LEFT JOIN users u3 ON u3.id=s.released_by "
                        "WHERE s.id=?", (sid,))
        if r is None:
            raise SessionError("Session not found")
        gp = self.gate_passes.get(r["gate_pass_id"]) if r["gate_pass_id"] else None
        return SessionSummary(r["id"], r["bay_id"], r["bay_name"], r["status"], r["started_at"], r["ended_at"],
                              r["plate_text"], r["plate_confidence"], r["plate_image"], gp, self.lines(sid),
                              r["sb"] or r["sbu"] or ("Auto" if r["auto_started"] else ""), r["cb"] or r["cbu"] or "",
                              r["rb"] or r["rbu"] or "", r["release_reason"] or "", r["clip_path"],
                              bool(r["auto_started"]), r["notes"])

    def search(self, date_from: float | None = None, date_to: float | None = None, plate: str = "",
               gate_pass: str = "", product_id: int | None = None, bay_id: int | None = None,
               status: str = "", include_deleted: bool = False, limit: int = 500):
        sql = ("SELECT s.id, s.started_at, s.ended_at, s.status, s.plate_text, b.name AS bay, g.number AS gate_pass, "
               "g.customer, s.result FROM sessions s JOIN bays b ON b.id=s.bay_id "
               "LEFT JOIN gate_passes g ON g.id=s.gate_pass_id WHERE 1=1")
        args: list = []
        if not include_deleted:
            sql += " AND s.deleted=0"
        if date_from:
            sql += " AND s.started_at>=?"; args.append(date_from)
        if date_to:
            sql += " AND s.started_at<?"; args.append(date_to)
        if plate:
            sql += " AND REPLACE(REPLACE(s.plate_text,'-',''),' ','') LIKE ?"
            args.append("%" + plate.replace("-", "").replace(" ", "") + "%")
        if gate_pass:
            sql += " AND g.number LIKE ?"; args.append(f"%{gate_pass}%")
        if bay_id:
            sql += " AND s.bay_id=?"; args.append(bay_id)
        if status:
            sql += " AND s.status=?"; args.append(status)
        if product_id:
            sql += (" AND (EXISTS (SELECT 1 FROM count_events e WHERE e.session_id=s.id AND e.product_id=?) OR "
                    "EXISTS (SELECT 1 FROM gate_pass_items i WHERE i.gate_pass_id=s.gate_pass_id AND i.product_id=?))")
            args += [product_id, product_id]
        sql += " ORDER BY s.started_at DESC LIMIT ?"
        args.append(limit)
        return self.db.q(sql, args)

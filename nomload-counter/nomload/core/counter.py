"""Direction-aware line/zone crossing counter.

Rules (each physical item is counted once):

* Every tracked item has a *committed side* of the line: OUTSIDE (-1) or
  INSIDE the truck (+1). It only changes when the item's centre moves past the
  line by more than a hysteresis ``band``. A labourer pausing on the line,
  swaying, or stepping back and forth inside the band never changes sides,
  so it never double counts.
* OUTSIDE -> INSIDE  = +1 (loaded).  INSIDE -> OUTSIDE = -1 (carried back out).
* Identity recovery: when the tracker loses an item (occlusion) and a new track
  ID appears close to where the old one was predicted to be, the new track
  inherits the old track's committed side - so an ID switch mid-crossing does
  not produce a second count.
* A track that is first seen inside the band (it appeared out of an occlusion
  right on the line) and then exits to the truck side is counted, but with low
  confidence so a supervisor reviews it.
* Every count gets a confidence score from detection scores, track length and
  how cleanly the crossing was observed. Counts under the review threshold are
  flagged instead of being silently accepted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nomload.core.geometry import PixelGeometry
from nomload.core.tracker import Track

OUTSIDE, UNKNOWN, INSIDE = -1, 0, 1


@dataclass
class CountEvent:
    track_id: int
    cls: str
    direction: int        # +1 loaded, -1 carried back out
    frame: int
    timestamp: float
    box: tuple
    confidence: float
    flagged: bool
    reason: str = ""


@dataclass
class _State:
    side: int
    born_in_band: bool
    inherited: bool = False
    counted_dir: int = 0
    last_pos: tuple = (0.0, 0.0)
    last_frame: int = 0
    size: float = 20.0


@dataclass
class CounterConfig:
    review_threshold: float = 0.45
    recover_frames: int = 20        # how long a lost track can be "re-found"
    recover_distance: float = 1.6   # in multiples of item height
    min_track_hits: int = 3


class LineCounter:
    def __init__(self, geometry: PixelGeometry, countable: set[str], config: CounterConfig | None = None):
        self.geo = geometry
        self.countable = set(countable)
        self.cfg = config or CounterConfig()
        self.states: dict[int, _State] = {}
        self.orphans: dict[int, _State] = {}  # states of lost tracks awaiting recovery
        self.totals: dict[str, int] = {}
        self.events: list[CountEvent] = []

    def reset(self):
        self.states.clear()
        self.orphans.clear()
        self.totals.clear()
        self.events.clear()

    def set_geometry(self, geometry: PixelGeometry):
        self.geo = geometry
        self.states.clear()
        self.orphans.clear()

    def _side_of(self, d: float) -> int:
        if d > self.geo.band:
            return INSIDE
        if d < -self.geo.band:
            return OUTSIDE
        return UNKNOWN

    def update(self, tracks: list[Track], lost: list[Track], frame: int, timestamp: float) -> list[CountEvent]:
        out: list[CountEvent] = []
        active_ids = set()
        for t in tracks:
            if t.cls not in self.countable:
                continue
            active_ids.add(t.track_id)
            c = t.center
            d = self.geo.signed_distance(c)
            side = self._side_of(d)
            h = max(8.0, float(t.box[3] - t.box[1]))
            st = self.states.get(t.track_id)
            if st is None:
                st = self._recover(t, c, frame, h)
                if st is None:
                    st = _State(side=side if side != UNKNOWN else UNKNOWN, born_in_band=(side == UNKNOWN))
                self.states[t.track_id] = st
            st.last_pos, st.last_frame, st.size = c, frame, h
            if side == UNKNOWN or not self.geo.within_segment(c):
                continue
            if st.side == UNKNOWN:
                if st.born_in_band and side == INSIDE and t.hits >= self.cfg.min_track_hits:
                    # appeared right on the line and went into the truck
                    ev = self._event(t, +1, frame, timestamp, uncertain=True, reason="appeared on line", force_flag=True)
                    out.append(ev)
                    st.counted_dir = 1
                st.side = side
                continue
            if side != st.side:
                direction = +1 if side == INSIDE else -1
                st.side = side
                if t.hits < self.cfg.min_track_hits:
                    reason = "short track"
                else:
                    reason = ""
                ev = self._event(t, direction, frame, timestamp, uncertain=bool(reason) or st.inherited,
                                 reason=reason or ("identity recovered" if st.inherited else ""),
                                 force_flag=bool(reason))
                st.counted_dir = direction
                out.append(ev)
        # tracks that disappeared become orphans for identity recovery
        for t in lost:
            if t.track_id in self.states and t.track_id not in active_ids:
                self.orphans[t.track_id] = self.states.pop(t.track_id)
        for tid in [k for k, s in self.orphans.items() if frame - s.last_frame > self.cfg.recover_frames]:
            del self.orphans[tid]
        for tid in [k for k in self.states if k not in active_ids and self.states[k].last_frame < frame - 2 * self.cfg.recover_frames]:
            del self.states[tid]
        self.events.extend(out)
        return out

    def _recover(self, t: Track, c, frame: int, h: float) -> _State | None:
        best, best_d = None, float("inf")
        for tid, s in self.orphans.items():
            dist = math.hypot(c[0] - s.last_pos[0], c[1] - s.last_pos[1])
            lim = self.cfg.recover_distance * max(h, s.size) + 4.0 * (frame - s.last_frame)
            if dist < lim and dist < best_d:
                best, best_d = tid, dist
        if best is None:
            return None
        s = self.orphans.pop(best)
        return _State(side=s.side, born_in_band=s.born_in_band, inherited=True, counted_dir=s.counted_dir,
                      last_pos=c, last_frame=frame, size=h)

    def _event(self, t: Track, direction: int, frame: int, ts: float, uncertain: bool, reason: str,
               force_flag: bool = False) -> CountEvent:
        score = t.mean_score
        length = min(1.0, t.hits / 8.0)
        conf = score * (0.55 + 0.45 * length)
        if force_flag:
            conf *= 0.6
        elif uncertain:
            # brief occlusion (labourer's arm/body) recovered by position: normal, slightly less certain
            conf *= 0.85
        conf = round(max(0.0, min(1.0, conf)), 3)
        flagged = force_flag or conf < self.cfg.review_threshold
        if flagged and not reason:
            reason = "low detection confidence"
        self.totals[t.cls] = self.totals.get(t.cls, 0) + direction
        b = t.box
        return CountEvent(t.track_id, t.cls, direction, frame, ts, tuple(float(v) for v in b), conf, flagged, reason)

    def net(self, cls: str | None = None) -> int:
        if cls is None:
            return sum(self.totals.values())
        return self.totals.get(cls, 0)

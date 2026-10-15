"""Counting engine: detection -> ignore zones -> ByteTrack -> line counter.

UI- and database-free so the same code runs in the live app, the evaluation
tool and the tests.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from nomload.config import COUNTABLE_CLASSES
from nomload.core.counter import CounterConfig, CountEvent, LineCounter
from nomload.core.detector import Detection, ModelRegistry
from nomload.core.geometry import CountGeometry, PixelGeometry
from nomload.core.tracker import ByteTracker, Track

CLASS_COLORS = {  # BGR
    "bag": (60, 170, 240), "carton": (40, 120, 200), "crate": (80, 80, 230), "pack": (200, 160, 60),
    "person": (170, 170, 170), "truck": (120, 90, 40), "plate": (60, 200, 60),
}
AMBER = (45, 163, 232)
NAVY = (78, 42, 27)


@dataclass
class EngineResult:
    frame: np.ndarray
    detections: list[Detection]
    tracks: list[Track]
    events: list[CountEvent]
    truck_present: bool
    plates: list[Detection]
    infer_ms: float
    frame_idx: int
    ts: float


@dataclass
class EngineConfig:
    max_width: int = 960
    review_threshold: float = 0.45
    countable: set = field(default_factory=lambda: set(COUNTABLE_CLASSES))
    truck_score: float = 0.5


class CountingEngine:
    def __init__(self, registry: ModelRegistry, geometry: CountGeometry, config: EngineConfig | None = None):
        self.registry = registry
        self.geometry = geometry
        self.cfg = config or EngineConfig()
        self.tracker = ByteTracker(self.cfg.countable)
        self._pix: PixelGeometry | None = None
        self._size = None
        self.counter: LineCounter | None = None
        self.frame_idx = 0
        self.flashes: list[tuple[float, tuple, int]] = []  # (ts, center, direction)
        self.last_truck_seen = 0.0

    # ------------------------------------------------------------------ setup
    def _ensure(self, w: int, h: int):
        if self._size != (w, h) or self.counter is None:
            self._size = (w, h)
            self._pix = self.geometry.to_pixels(w, h)
            if self.counter is None:
                self.counter = LineCounter(self._pix, self.cfg.countable,
                                           CounterConfig(review_threshold=self.cfg.review_threshold))
            else:
                self.counter.set_geometry(self._pix)

    def set_geometry(self, geometry: CountGeometry):
        self.geometry = geometry
        self._size = None

    def reset_counts(self):
        if self.counter:
            self.counter.reset()
        self.tracker.reset()
        self.flashes.clear()

    def prepare(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if w > self.cfg.max_width:
            nh = int(h * self.cfg.max_width / w)
            frame = cv2.resize(frame, (self.cfg.max_width, nh), interpolation=cv2.INTER_AREA)
        return frame

    # ------------------------------------------------------------------ main
    def process(self, frame: np.ndarray, ts: float | None = None) -> EngineResult:
        ts = time.time() if ts is None else ts
        frame = self.prepare(frame)
        h, w = frame.shape[:2]
        self._ensure(w, h)
        self.frame_idx += 1
        det = self.registry.detector
        t0 = time.perf_counter()
        dets = det.detect(frame) if det else []
        infer_ms = (time.perf_counter() - t0) * 1000
        pix = self._pix
        kept = [d for d in dets if not pix.ignored(d.center)]
        goods_people = [d for d in kept if d.cls in self.cfg.countable or d.cls == "person"]
        tracks = self.tracker.update(goods_people)
        events = self.counter.update(tracks, self.tracker.lost_tracks, self.frame_idx, ts)
        for e in events:
            b = e.box
            self.flashes.append((ts, ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), e.direction))
        trucks = [d for d in kept if d.cls == "truck" and d.score >= self.cfg.truck_score]
        if trucks:
            self.last_truck_seen = ts
        plates = [d for d in dets if d.cls == "plate"]
        return EngineResult(frame, kept, tracks, events, bool(trucks), plates, infer_ms, self.frame_idx, ts)

    # ------------------------------------------------------------------ overlay
    def annotate(self, res: EngineResult, show_people: bool = True) -> np.ndarray:
        img = res.frame.copy()
        pix = self._pix
        if pix is None:
            return img
        h, w = img.shape[:2]
        th = max(2, w // 320)
        # ignore zones
        for z in pix.ignore_zones:
            if len(z) >= 3:
                pts = np.array(z, np.int32)
                ov = img.copy()
                cv2.fillPoly(ov, [pts], (90, 90, 90))
                img = cv2.addWeighted(ov, 0.35, img, 0.65, 0)
                cv2.polylines(img, [pts], True, (160, 160, 160), 1, cv2.LINE_AA)
        if pix.plate_roi:
            x0, y0, x1, y1 = pix.plate_roi
            cv2.rectangle(img, (x0, y0), (x1, y1), (60, 200, 60), 1, cv2.LINE_AA)
        # counting line / zone with direction arrow
        if pix.mode == "zone" and len(pix.zone) >= 3:
            cv2.polylines(img, [np.array(pix.zone, np.int32)], True, AMBER, th + 1, cv2.LINE_AA)
        else:
            p1 = tuple(int(v) for v in pix.p1)
            p2 = tuple(int(v) for v in pix.p2)
            band = int(pix.band)
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L  # left normal
            # direction: point on the "inside" side
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            if pix.signed_distance((mid[0] + nx * 10, mid[1] + ny * 10)) < 0:
                nx, ny = -nx, -ny
            ov = img.copy()
            poly = np.array([[p1[0] - nx * band, p1[1] - ny * band], [p2[0] - nx * band, p2[1] - ny * band],
                             [p2[0] + nx * band, p2[1] + ny * band], [p1[0] + nx * band, p1[1] + ny * band]], np.int32)
            cv2.fillPoly(ov, [poly], AMBER)
            img = cv2.addWeighted(ov, 0.18, img, 0.82, 0)
            cv2.line(img, p1, p2, AMBER, th + 1, cv2.LINE_AA)
            a0 = (int(mid[0] - nx * 18), int(mid[1] - ny * 18))
            a1 = (int(mid[0] + nx * 40), int(mid[1] + ny * 40))
            cv2.arrowedLine(img, a0, a1, AMBER, th + 1, cv2.LINE_AA, tipLength=0.35)
        # tracks
        fs = max(0.4, w / 1600)
        for t in res.tracks:
            if t.cls == "person" and not show_people:
                continue
            x0, y0, x1, y1 = [int(v) for v in t.box]
            col = CLASS_COLORS.get(t.cls, (0, 200, 255))
            cv2.rectangle(img, (x0, y0), (x1, y1), col, 1 if t.cls == "person" else th, cv2.LINE_AA)
            if t.cls != "person":
                label = f"{t.cls} #{t.track_id}"
                (tw, tht), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
                cv2.rectangle(img, (x0, y0 - tht - 4), (x0 + tw + 4, y0), col, -1)
                cv2.putText(img, label, (x0 + 2, y0 - 3), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 1, cv2.LINE_AA)
        trucks = sorted((d for d in res.detections if d.cls == "truck"), key=lambda d: -d.score)[:1]
        for d in trucks:
            if d.cls == "truck":
                cv2.rectangle(img, (int(d.x0), int(d.y0)), (int(d.x1), int(d.y1)), CLASS_COLORS["truck"], 1, cv2.LINE_AA)
        # count flashes (+1 / -1)
        now = res.ts
        self.flashes = [f for f in self.flashes if now - f[0] < 1.2]
        for t0, (cx, cy), d in self.flashes:
            k = (now - t0) / 1.2
            col = (60, 190, 60) if d > 0 else (50, 50, 220)
            txt = "+1" if d > 0 else "-1"
            cv2.putText(img, txt, (int(cx - 12), int(cy - 20 - 30 * k)), cv2.FONT_HERSHEY_DUPLEX, fs * 2.2, col, 2,
                        cv2.LINE_AA)
        stamp = time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(res.ts))
        sfs = max(0.45, fs)
        (tw, tht), _b = cv2.getTextSize(stamp, cv2.FONT_HERSHEY_SIMPLEX, sfs, 1)
        cv2.rectangle(img, (4, h - tht - 14), (tw + 14, h - 4), (20, 20, 20), -1)
        cv2.putText(img, stamp, (9, h - 9), cv2.FONT_HERSHEY_SIMPLEX, sfs, (255, 255, 255), 1, cv2.LINE_AA)
        return img

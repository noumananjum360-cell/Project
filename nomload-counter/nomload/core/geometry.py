"""Geometry helpers for counting lines, zones and regions (frame pixel coords)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

Point = tuple[float, float]


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), np.float32)
    a = a[:, None, :]
    b = b[None, :, :]
    x0 = np.maximum(a[..., 0], b[..., 0])
    y0 = np.maximum(a[..., 1], b[..., 1])
    x1 = np.minimum(a[..., 2], b[..., 2])
    y1 = np.minimum(a[..., 3], b[..., 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    area_a = (a[..., 2] - a[..., 0]) * (a[..., 3] - a[..., 1])
    area_b = (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
    return inter / np.maximum(area_a + area_b - inter, 1e-6)


def point_in_polygon(pt: Point, poly: list[Point]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def polygon_signed_distance(pt: Point, poly: list[Point]) -> float:
    """Positive inside, negative outside (distance to nearest edge)."""
    best = float("inf")
    n = len(poly)
    for i in range(n):
        best = min(best, _seg_dist(pt, poly[i], poly[(i + 1) % n]))
    return best if point_in_polygon(pt, poly) else -best


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


@dataclass
class CountGeometry:
    """Calibrated counting geometry for one camera.

    mode 'line': a segment p1->p2. ``in_side`` (+1/-1) says which side of the
    line is "inside the truck" (the side the direction arrow points to).
    mode 'zone': a polygon; entering the polygon counts as loading.
    All coordinates are normalised (0..1) so calibration survives resolution
    changes; use ``to_pixels`` before counting.
    """
    mode: str = "line"
    p1: Point = (0.68, 0.15)
    p2: Point = (0.68, 0.95)
    in_side: int = 1
    zone: list[Point] = field(default_factory=list)
    ignore_zones: list[list[Point]] = field(default_factory=list)
    plate_roi: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 normalised
    band: float = 0.022   # hysteresis half-width as a fraction of frame width
    segment_margin: float = 0.08

    def to_dict(self) -> dict:
        return {"mode": self.mode, "p1": list(self.p1), "p2": list(self.p2), "in_side": self.in_side,
                "zone": [list(p) for p in self.zone], "ignore_zones": [[list(p) for p in z] for z in self.ignore_zones],
                "plate_roi": list(self.plate_roi) if self.plate_roi else None, "band": self.band,
                "segment_margin": self.segment_margin}

    @classmethod
    def from_dict(cls, d: dict | None) -> "CountGeometry":
        if not d:
            return cls()
        return cls(mode=d.get("mode", "line"), p1=tuple(d.get("p1", (0.68, 0.15))), p2=tuple(d.get("p2", (0.68, 0.95))),
                   in_side=int(d.get("in_side", 1)), zone=[tuple(p) for p in d.get("zone", [])],
                   ignore_zones=[[tuple(p) for p in z] for z in d.get("ignore_zones", [])],
                   plate_roi=tuple(d["plate_roi"]) if d.get("plate_roi") else None,
                   band=float(d.get("band", 0.022)), segment_margin=float(d.get("segment_margin", 0.08)))

    def to_pixels(self, w: int, h: int) -> "PixelGeometry":
        sc = lambda p: (p[0] * w, p[1] * h)  # noqa: E731
        roi = None
        if self.plate_roi:
            x0, y0, x1, y1 = self.plate_roi
            roi = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
        return PixelGeometry(self.mode, sc(self.p1), sc(self.p2), self.in_side, [sc(p) for p in self.zone],
                             [[sc(p) for p in z] for z in self.ignore_zones], roi, self.band * w,
                             self.segment_margin)


@dataclass
class PixelGeometry:
    mode: str
    p1: Point
    p2: Point
    in_side: int
    zone: list[Point]
    ignore_zones: list[list[Point]]
    plate_roi: tuple[int, int, int, int] | None
    band: float
    segment_margin: float

    def signed_distance(self, pt: Point) -> float:
        """Distance with positive values on the 'inside the truck' side."""
        if self.mode == "zone" and len(self.zone) >= 3:
            return polygon_signed_distance(pt, self.zone)
        (x1, y1), (x2, y2) = self.p1, self.p2
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1.0
        cross = (dx * (pt[1] - y1) - dy * (pt[0] - x1)) / L
        # convention: in_side=+1 means the side to the *right* when walking p1->p2 in image
        # coords (y down) which for a top-to-bottom line is the left of the screen; we flip so
        # that the default vertical line with in_side=+1 has the truck on the right.
        return -cross * self.in_side

    def within_segment(self, pt: Point) -> bool:
        if self.mode == "zone":
            return True
        (x1, y1), (x2, y2) = self.p1, self.p2
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1.0
        t = ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / L2
        return -self.segment_margin <= t <= 1 + self.segment_margin

    def ignored(self, pt: Point) -> bool:
        return any(point_in_polygon(pt, z) for z in self.ignore_zones if len(z) >= 3)

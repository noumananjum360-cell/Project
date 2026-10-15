"""Synthetic loading-bay scene generator.

Produces side-view CCTV-like footage of labourers loading a truck the way it
happens in Pakistani mills and depots: bags carried on the head, shoulder or
back, cartons stacked in the arms, hand trolleys with several items, a belt
conveyor, workers pausing on the line, several workers crossing at once and the
occasional item carried back out of the truck (a correction, counts -1).

Every rendered frame comes with exact bounding boxes, so the same code is used
to (a) build training data for the starter detector and (b) produce sample test
videos with an answer-key CSV of the true counts.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from nomload.config import DEFAULT_CLASSES

W, H = 640, 360
LINE_X = 440          # counting line used by the sample videos
TRUCK_X0 = 482        # truck rear opening starts here

BAG_STYLES = {
    "cement": ((112, 139, 156), (60, 70, 160)),     # kraft grey-brown, red print (BGR)
    "flour": ((222, 228, 232), (40, 140, 40)),      # off-white woven, green band
    "fertilizer": ((235, 235, 235), (170, 90, 20)),  # white, blue band
    "sugar": ((230, 232, 228), (40, 40, 190)),      # white, red band
    "rice": ((170, 205, 220), (30, 100, 160)),       # beige, brown print
}
PRODUCT_OF_STYLE = {
    "cement": "Cement 50kg bag",
    "flour": "Flour 50kg bag",
    "fertilizer": "Urea 50kg bag",
    "sugar": "Sugar 50kg bag",
    "rice": "Rice 25kg bag",
    "carton": "Carton 1.5L x6",
    "crate": "Beverage crate x24",
    "pack": "Shrink pack 500ml x12",
}
CLASS_OF_STYLE = {**{k: "bag" for k in BAG_STYLES}, "carton": "carton", "crate": "crate", "pack": "pack"}
SHIRTS = [(200, 200, 205), (90, 120, 160), (60, 90, 60), (150, 150, 120), (40, 40, 140), (120, 80, 50),
          (180, 170, 150), (70, 70, 70), (160, 110, 90), (100, 140, 170)]
SKINS = [(80, 120, 170), (70, 105, 150), (95, 140, 190), (60, 90, 130)]


# --------------------------------------------------------------------------- items
@dataclass
class Item:
    style: str
    w: float
    h: float
    angle: float = 0.0

    @property
    def cls(self) -> str:
        return CLASS_OF_STYLE[self.style]


def _shade(c, f):
    return tuple(int(max(0, min(255, v * f))) for v in c)


def draw_item(img: np.ndarray, item: Item, cx: float, cy: float, rng_seed: int = 0) -> tuple[int, int, int, int]:
    """Draw an item centred at (cx, cy); returns its axis aligned bbox."""
    w, h = item.w, item.h
    rect = ((cx, cy), (w, h), item.angle)
    pts = cv2.boxPoints(rect).astype(np.int32)
    st = item.style
    if st in BAG_STYLES:
        base, band = BAG_STYLES[st]
        cv2.fillPoly(img, [pts], base, cv2.LINE_AA)
        # puffy edges: darker outline + seam
        cv2.polylines(img, [pts], True, _shade(base, 0.6), 2, cv2.LINE_AA)
        # printed band across the middle
        bw = (w * 0.9, h * 0.32)
        band_pts = cv2.boxPoints(((cx, cy), bw, item.angle)).astype(np.int32)
        cv2.fillPoly(img, [band_pts], band, cv2.LINE_AA)
        # woven texture stripes
        a = math.radians(item.angle)
        for k in (-0.35, 0.35):
            dx, dy = math.cos(a) * w * k, math.sin(a) * w * k
            p1 = (int(cx + dx - math.sin(a) * h * 0.45), int(cy + dy + math.cos(a) * h * 0.45))
            p2 = (int(cx + dx + math.sin(a) * h * 0.45), int(cy + dy - math.cos(a) * h * 0.45))
            cv2.line(img, p1, p2, _shade(base, 0.8), 1, cv2.LINE_AA)
    elif st == "carton":
        cv2.fillPoly(img, [pts], (79, 123, 168), cv2.LINE_AA)
        cv2.polylines(img, [pts], True, (40, 70, 100), 2, cv2.LINE_AA)
        tape = cv2.boxPoints(((cx, cy), (w * 0.18, h * 0.96), item.angle)).astype(np.int32)
        cv2.fillPoly(img, [tape], (130, 170, 205), cv2.LINE_AA)
        cv2.putText(img, "1.5L", (int(cx - w * 0.42), int(cy + h * 0.3)), cv2.FONT_HERSHEY_PLAIN,
                    max(0.5, h / 40), (30, 50, 70), 1, cv2.LINE_AA)
    elif st == "crate":
        color = [(40, 40, 200), (180, 90, 30), (30, 190, 220)][rng_seed % 3]
        cv2.fillPoly(img, [pts], color, cv2.LINE_AA)
        cv2.polylines(img, [pts], True, _shade(color, 0.5), 2, cv2.LINE_AA)
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        for i in range(4):
            for j in range(2):
                hx = int(x0 + w * (0.12 + i * 0.22))
                hy = int(y0 + h * (0.25 + j * 0.38))
                cv2.rectangle(img, (hx, hy), (hx + max(2, int(w * 0.12)), hy + max(2, int(h * 0.2))),
                              _shade(color, 0.45), -1)
    elif st == "pack":
        cv2.fillPoly(img, [pts], (200, 185, 160), cv2.LINE_AA)
        x0, y0 = cx - w / 2, cy - h / 2
        r = max(2, int(min(w / 8, h / 4)))
        for i in range(4):
            for j in range(2):
                c = (int(x0 + w * (0.14 + i * 0.24)), int(y0 + h * (0.3 + j * 0.42)))
                cv2.circle(img, c, r, (150, 110, 60), -1, cv2.LINE_AA)
                cv2.circle(img, (c[0] - 1, c[1] - 1), max(1, r // 3), (250, 250, 250), -1, cv2.LINE_AA)
        cv2.polylines(img, [pts], True, (230, 225, 215), 1, cv2.LINE_AA)
    x0, y0 = pts[:, 0].min(), pts[:, 1].min()
    x1, y1 = pts[:, 0].max(), pts[:, 1].max()
    return int(x0), int(y0), int(x1), int(y1)


def make_item(style: str, rng: random.Random, scale: float) -> Item:
    if style in BAG_STYLES:
        return Item(style, rng.uniform(48, 58) * scale, rng.uniform(22, 27) * scale)
    if style == "carton":
        return Item(style, rng.uniform(32, 38) * scale, rng.uniform(21, 25) * scale)
    if style == "crate":
        return Item(style, rng.uniform(40, 46) * scale, rng.uniform(22, 26) * scale)
    return Item(style, rng.uniform(38, 44) * scale, rng.uniform(20, 23) * scale)


# --------------------------------------------------------------------------- actors
@dataclass
class Trip:
    """A labourer (or trolley/conveyor item group) moving horizontally."""
    kind: str               # head|shoulder|back|arms|trolley|empty|conveyor
    t0: float               # start time (s)
    y: float                # feet baseline
    x_start: float
    x_end: float
    speed: float            # px/s (absolute)
    items: list[Item] = field(default_factory=list)
    pause_at: float | None = None   # x where the worker pauses
    pause_s: float = 0.0
    shirt: tuple = (200, 200, 200)
    skin: tuple = (80, 120, 170)
    seed: int = 0
    style: str = "flour"

    @property
    def direction(self) -> int:
        return 1 if self.x_end > self.x_start else -1

    @property
    def scale(self) -> float:
        return 0.82 + (self.y - 230) / 130 * 0.28

    def duration(self) -> float:
        return abs(self.x_end - self.x_start) / self.speed + self.pause_s

    def x_at(self, t: float) -> float | None:
        dt = t - self.t0
        if dt < 0 or dt > self.duration():
            return None
        d = self.direction
        if self.pause_at is None:
            return self.x_start + d * self.speed * dt
        t_pause = abs(self.pause_at - self.x_start) / self.speed
        if dt < t_pause:
            return self.x_start + d * self.speed * dt
        if dt < t_pause + self.pause_s:
            # sway while standing on the line
            return self.pause_at + 3.0 * math.sin((dt - t_pause) * 5.0 + self.seed)
        return self.pause_at + d * self.speed * (dt - t_pause - self.pause_s)

    def item_offsets(self) -> list[tuple[float, float, float]]:
        """(dx, dy, angle) of each carried item relative to the feet point."""
        s, d = self.scale, self.direction
        body_h = 118 * s
        if self.kind == "head":
            return [(0, -body_h - 9 * s, 0)]
        if self.kind == "shoulder":
            return [(d * 13 * s, -body_h + 26 * s, 18 * d)]
        if self.kind == "back":
            return [(-d * 15 * s, -body_h + 45 * s, 90)]
        if self.kind == "arms":
            out = []
            for i, it in enumerate(self.items):
                out.append((d * 20 * s, -body_h * 0.48 - i * (it.h + 0.5), 0))
            return out
        if self.kind in ("trolley", "conveyor"):
            out = []
            n = len(self.items)
            cols = 1 if self.kind == "conveyor" else min(3, max(1, (n + 1) // 2))
            for i, it in enumerate(self.items):
                r, c = divmod(i, cols)
                base = d * 48 * s if self.kind == "trolley" else 0
                dx = base + (c - (cols - 1) / 2) * (it.w + 2)
                out.append((dx, -14 * s - r * (it.h + 0.5) - it.h / 2, 0))
            return out
        return []


def _draw_worker(img, x, y, tr: Trip, t: float):
    s = tr.scale
    body_h = 118 * s
    d = tr.direction
    phase = (x / max(8.0, 14 * s))
    leg = 9 * s * math.sin(phase)
    pants = _shade(tr.shirt, 0.85)
    cv2.line(img, (int(x), int(y - body_h * 0.45)), (int(x + leg), int(y)), pants, max(2, int(8 * s)), cv2.LINE_AA)
    cv2.line(img, (int(x), int(y - body_h * 0.45)), (int(x - leg), int(y)), _shade(pants, 0.8), max(2, int(8 * s)), cv2.LINE_AA)
    # kameez (long shirt)
    top = int(y - body_h + 22 * s)
    cv2.rectangle(img, (int(x - 14 * s), top), (int(x + 14 * s), int(y - body_h * 0.32)), tr.shirt, -1, cv2.LINE_AA)
    # arms raised when carrying on head
    arm_col = _shade(tr.shirt, 0.9)
    if tr.kind == "head":
        cv2.line(img, (int(x - 10 * s), top + 4), (int(x - 14 * s), int(y - body_h - 4 * s)), arm_col, max(2, int(6 * s)), cv2.LINE_AA)
        cv2.line(img, (int(x + 10 * s), top + 4), (int(x + 14 * s), int(y - body_h - 4 * s)), arm_col, max(2, int(6 * s)), cv2.LINE_AA)
    elif tr.kind in ("arms", "trolley"):
        cv2.line(img, (int(x), top + 6), (int(x + d * 24 * s), int(y - body_h * 0.5)), arm_col, max(2, int(6 * s)), cv2.LINE_AA)
    else:
        sw = 6 * s * math.sin(phase + 1.5)
        cv2.line(img, (int(x), top + 6), (int(x + sw), int(y - body_h * 0.42)), arm_col, max(2, int(6 * s)), cv2.LINE_AA)
    # head
    cv2.circle(img, (int(x), int(y - body_h + 10 * s)), max(3, int(10 * s)), tr.skin, -1, cv2.LINE_AA)
    if tr.seed % 3 == 0:  # topi / cap
        cv2.ellipse(img, (int(x), int(y - body_h + 4 * s)), (int(10 * s), int(5 * s)), 0, 180, 360, (230, 230, 230), -1)
    return (int(x - 16 * s), int(y - body_h - 1 * s), int(x + 16 * s), int(y))


def _draw_trolley(img, x, y, tr: Trip):
    s, d = tr.scale, tr.direction
    x0 = x + d * 20 * s
    x1 = x + d * 78 * s
    a, b = int(min(x0, x1)), int(max(x0, x1))
    cv2.rectangle(img, (a, int(y - 12 * s)), (b, int(y - 6 * s)), (60, 60, 70), -1)
    cv2.line(img, (int(x0), int(y - 8 * s)), (int(x + d * 8 * s), int(y - 60 * s)), (60, 60, 70), max(2, int(3 * s)))
    for wx in (a + 6 * s, b - 6 * s):
        cv2.circle(img, (int(wx), int(y - 3 * s)), max(2, int(4 * s)), (30, 30, 30), -1)


# --------------------------------------------------------------------------- background
def make_background(rng: random.Random, truck: bool = True, plate_text: str | None = None,
                    line_x: int = LINE_X) -> tuple[np.ndarray, list]:
    img = np.zeros((H, W, 3), np.uint8)
    wall = np.array([rng.randint(150, 190), rng.randint(155, 195), rng.randint(160, 200)], np.uint8)
    img[:170] = wall
    floor = np.array([rng.randint(110, 140)] * 3, np.uint8)
    for y in range(170, H):
        img[y] = (floor * (0.85 + 0.25 * (y - 170) / 190)).clip(0, 255)
    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 6, (H, W, 1))
    img = (img.astype(np.float32) + noise).clip(0, 255).astype(np.uint8)
    # floor joints
    for x in range(-200, W, 90):
        cv2.line(img, (x + 200, 170), (x, H), (95, 95, 95), 1, cv2.LINE_AA)
    # stock pile on the left (stack of bags/cartons, static, *not labelled*)
    pile_style = rng.choice(list(BAG_STYLES) + ["carton"])
    base_col = BAG_STYLES.get(pile_style, ((79, 123, 168), None))[0]
    for r in range(5):
        for c in range(3):
            x = 8 + c * 34 + (r % 2) * 14
            y = 205 - r * 18
            cv2.rectangle(img, (x, y), (x + 32, y + 16), _shade(base_col, 0.75 + 0.05 * ((r + c) % 3)), -1)
            cv2.rectangle(img, (x, y), (x + 32, y + 16), _shade(base_col, 0.5), 1)
    # pillar
    px = rng.randint(180, 300)
    cv2.rectangle(img, (px, 0), (px + 14, 175), _shade(wall, 0.8), -1)
    boxes = []
    if truck:
        tx0 = TRUCK_X0
        body = (rng.randint(30, 90), rng.randint(60, 140), rng.randint(120, 200))
        cv2.rectangle(img, (tx0, 30), (W, 330), body, -1)
        cv2.rectangle(img, (tx0 + 14, 50), (W, 300), (25, 28, 32), -1)   # dark cargo opening
        # truck art stripes (Pakistani trucks are colourful)
        for i, col in enumerate([(0, 200, 255), (40, 40, 220), (60, 170, 30), (200, 80, 20)]):
            cv2.rectangle(img, (tx0, 30 + i * 5), (W, 34 + i * 5), col, -1)
        cv2.rectangle(img, (tx0, 300), (W, 330), _shade(body, 0.7), -1)  # tailgate
        if plate_text:
            cv2.rectangle(img, (tx0 + 40, 306), (tx0 + 110, 324), (235, 235, 235), -1)
            cv2.putText(img, plate_text, (tx0 + 42, 320), cv2.FONT_HERSHEY_PLAIN, 0.8, (10, 10, 10), 1, cv2.LINE_AA)
            boxes.append(("plate", (tx0 + 40, 306, tx0 + 110, 324)))
        boxes.append(("truck", (tx0, 30, W - 1, 330)))
    return img, boxes


# --------------------------------------------------------------------------- scene
@dataclass
class Scene:
    trips: list[Trip]
    background: np.ndarray
    static_boxes: list
    duration: float
    line_x: int = LINE_X
    seed: int = 0
    conveyor_y: float | None = None

    def render(self, t: float, noise_rng: np.random.Generator | None = None,
               shake: bool = True) -> tuple[np.ndarray, list]:
        img = self.background.copy()
        boxes = list(self.static_boxes)
        if self.conveyor_y is not None:
            cy = int(self.conveyor_y)
            belt_img = img
            cv2.rectangle(belt_img, (150, cy - 4), (self.line_x + 70, cy + 6), (50, 50, 55), -1)
            for k in range(150, self.line_x + 70, 16):
                off = int((t * 70) % 16)
                cv2.line(belt_img, (k + off, cy - 4), (k + off, cy + 6), (80, 80, 85), 1)
            cv2.rectangle(belt_img, (150, cy + 6), (self.line_x + 70, cy + 30), (90, 90, 95), -1)
        active = []
        for tr in self.trips:
            x = tr.x_at(t)
            if x is not None:
                active.append((tr.y, tr, x))
        active.sort(key=lambda a: a[0])
        for _, tr, x in active:
            y = tr.y
            if tr.kind != "conveyor":
                pb = _draw_worker(img, x, y, tr, t)
                if tr.kind == "trolley":
                    _draw_trolley(img, x, y, tr)
                boxes.append(("person", pb))
            for it, (dx, dy, ang) in zip(tr.items, tr.item_offsets()):
                it.angle = ang
                cx, cy = x + dx, y + dy
                if cx > TRUCK_X0 + 70 or cx < -30:
                    continue
                bb = draw_item(img, it, cx, cy, tr.seed)
                boxes.append((it.cls, bb))
        if shake:
            r = noise_rng or np.random.default_rng()
            dx, dy = r.integers(-1, 2), r.integers(-1, 2)
            if dx or dy:
                m = np.float32([[1, 0, dx], [0, 1, dy]])
                img = cv2.warpAffine(img, m, (W, H), borderMode=cv2.BORDER_REPLICATE)
                boxes = [(c, (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)) for c, b in boxes]
        r = noise_rng or np.random.default_rng()
        img = (img.astype(np.float32) * r.uniform(0.94, 1.06) + r.normal(0, 1.5, img.shape)).clip(0, 255).astype(np.uint8)
        clipped = []
        for c, (x0, y0, x1, y1) in boxes:
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W - 1, x1), min(H - 1, y1)
            if x1 - x0 >= 4 and y1 - y0 >= 4:
                clipped.append((c, (x0, y0, x1, y1)))
        return img, clipped

    def answer_key(self) -> dict[str, dict[str, int]]:
        """True per-product IN/OUT counts across the counting line."""
        res: dict[str, dict[str, int]] = {}
        for tr in self.trips:
            if not tr.items:
                continue
            crosses = (tr.x_start < self.line_x < tr.x_end) or (tr.x_end < self.line_x < tr.x_start)
            if not crosses:
                continue
            for it in tr.items:
                p = PRODUCT_OF_STYLE[it.style]
                d = res.setdefault(p, {"in": 0, "out": 0, "class": CLASS_OF_STYLE[it.style]})
                if tr.direction > 0:
                    d["in"] += 1
                else:
                    d["out"] += 1
        return res


def build_scene(seed: int, duration: float = 45.0, recipe: str = "mixed", line_x: int = LINE_X,
                truck: bool = True, plate_text: str | None = None, density: float = 1.0) -> Scene:
    """Create a randomised loading scene.

    recipe: 'bags' (flour mill), 'cartons' (FMCG), 'mixed', 'conveyor' or 'random'.
    """
    rng = random.Random(seed)
    if recipe == "random":
        recipe = rng.choice(["bags", "cartons", "mixed", "conveyor"])
    bg, static = make_background(rng, truck=truck, plate_text=plate_text, line_x=line_x)
    trips: list[Trip] = []
    lanes = [250, 285, 320, 345]
    lane_free = {y: 0.0 for y in lanes}
    bag_style = rng.choice(list(BAG_STYLES))
    t = 0.5
    conveyor_y = None
    if recipe == "conveyor":
        # belt in the foreground (closest to the camera) so labourers never hide it
        conveyor_y = 338.0
        lanes = [240, 262, 285, 305]
        lane_free = {y: 0.0 for y in lanes}
    while t < duration - 6:
        lane = rng.choice(lanes)
        start = max(t, lane_free[lane])
        if start > duration - 7:
            t += 0.5
            continue
        mode_roll = rng.random()
        if recipe == "bags":
            kind = rng.choice(["head", "head", "shoulder", "back"])
            styles = [bag_style]
        elif recipe == "cartons":
            kind = rng.choice(["arms", "arms", "trolley"])
            styles = ["carton", "pack"]
        elif recipe == "conveyor":
            kind = rng.choice(["arms", "head", "trolley"])
            styles = ["crate", "carton"] if kind != "head" else [bag_style]
        else:
            kind = rng.choice(["head", "shoulder", "back", "arms", "trolley"])
            styles = [bag_style] if kind in ("head", "shoulder", "back") else ["carton", "crate", "pack"]
        speed = rng.uniform(55, 95)
        trip = Trip(kind, start, lane, -40, TRUCK_X0 + 80, speed, shirt=rng.choice(SHIRTS),
                    skin=rng.choice(SKINS), seed=rng.randint(0, 999))
        style = rng.choice(styles)
        trip.style = style
        if kind in ("head", "shoulder", "back"):
            trip.items = [make_item(style, rng, trip.scale)]
        elif kind == "arms":
            trip.items = [make_item(style, rng, trip.scale) for _ in range(rng.choice([1, 2, 2, 3]))]
        else:
            trip.items = [make_item(style, rng, trip.scale) for _ in range(rng.choice([4, 4, 6]))]
        # some labourers stop on the line to talk / adjust the load
        if mode_roll < 0.18:
            trip.pause_at = line_x + rng.uniform(-14, 14)
            trip.pause_s = rng.uniform(1.0, 2.8)
        trips.append(trip)
        end_in = start + trip.duration()
        # walk back out empty (or, sometimes, carrying an item back = correction)
        back = Trip("empty", end_in + rng.uniform(1.0, 3.0), rng.choice(lanes), TRUCK_X0 + 80, -40,
                    rng.uniform(70, 110), shirt=trip.shirt, skin=trip.skin, seed=trip.seed)
        if rng.random() < 0.07 and kind in ("head", "shoulder", "arms"):
            back.kind = "head" if kind != "arms" else "arms"
            back.items = [make_item(style, rng, back.scale)]
            back.style = style
        if back.t0 + back.duration() < duration:
            trips.append(back)
        lane_free[lane] = start + 36 / speed * 3 + rng.uniform(0.6, 1.8)
        t = start + rng.uniform(0.6, 2.6) / density
    if conveyor_y is not None:
        ct = 1.0
        while ct < duration - 9:
            it = make_item(rng.choice(["carton", "pack"]), rng, 0.95)
            tr = Trip("conveyor", ct, conveyor_y, 160, TRUCK_X0 + 80, 70.0, items=[it], seed=rng.randint(0, 99))
            trips.append(tr)
            ct += rng.uniform(1.4, 3.2)
    # drop trips whose items would not finish inside the clip
    trips = [tr for tr in trips if tr.t0 + tr.duration() <= duration + 0.01]
    return Scene(trips, bg, static, duration, line_x, seed, conveyor_y)


# --------------------------------------------------------------------------- exports
def write_video(scene: Scene, path: Path, fps: int = 15, preroll_empty: float = 0.0) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    n = int(scene.duration * fps)
    nr = np.random.default_rng(scene.seed)
    for i in range(n):
        frame, _ = scene.render(i / fps, nr)
        vw.write(frame)
    vw.release()
    return n


def write_answer_key(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["video", "product", "class", "true_in", "true_out", "true_net"])
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def plate_scene_frames(seed: int, plate_text: str, province: str, duration: float = 10.0, fps: int = 15):
    """Close-up 'plate camera' view of a truck rear arriving and standing."""
    from nomload.training.qt_render import render_plate
    rng = random.Random(seed)
    style = rng.choice(["white", "white", "yellow", "green"])
    plate = render_plate(plate_text, province, style)
    nr = np.random.default_rng(seed)
    body = (rng.randint(20, 80), rng.randint(60, 150), rng.randint(140, 220))
    for i in range(int(duration * fps)):
        t = i / fps
        img = np.full((H, W, 3), 120, np.uint8)
        img[200:] = (90, 92, 95)
        z = min(1.0, 0.55 + t / 3.0 * 0.45)
        cx, cy = W // 2, int(150 + 30 * z)
        tw, th = int(420 * z), int(300 * z)
        x0, y0 = cx - tw // 2, cy - th // 2
        cv2.rectangle(img, (x0, y0), (x0 + tw, y0 + th), body, -1)
        for k, col in enumerate([(0, 200, 255), (40, 40, 220), (60, 170, 30), (200, 80, 20), (0, 140, 255)]):
            yy = y0 + int(th * (0.08 + 0.06 * k))
            cv2.rectangle(img, (x0, yy), (x0 + tw, yy + max(2, int(8 * z))), col, -1)
        cv2.rectangle(img, (x0, y0 + int(th * 0.75)), (x0 + tw, y0 + th), _shade(body, 0.6), -1)
        pw, ph = int(190 * z), int(62 * z)
        pl = cv2.resize(plate, (pw, ph), interpolation=cv2.INTER_AREA)
        px, py = cx - pw // 2, y0 + int(th * 0.78)
        if py + ph < H and px >= 0:
            img[py:py + ph, px:px + pw] = pl
        boxes = [("truck", (max(0, x0), max(0, y0), min(W - 1, x0 + tw), min(H - 1, y0 + th))),
                 ("plate", (px, py, px + pw, py + ph))]
        img = (img.astype(np.float32) * nr.uniform(0.9, 1.1) + nr.normal(0, 3, img.shape)).clip(0, 255).astype(np.uint8)
        if rng.random() < 0.3:
            img = cv2.GaussianBlur(img, (3, 3), 0)
        yield img, boxes


def write_plate_video(path: Path, seed: int, plate_text: str, province: str, fps: int = 15) -> None:
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    for img, _ in plate_scene_frames(seed, plate_text, province, fps=fps):
        vw.write(img)
    vw.release()


def training_samples(n: int, seed: int = 1000, classes: list[str] | None = None, recipes: list[str] | None = None,
                     density: tuple[float, float] = (0.8, 1.6)):
    """Yield (frame_bgr, [(class_idx, x0, y0, x1, y1), ...]) for detector training."""
    from nomload.core.plate_formats import random_plate
    classes = classes or DEFAULT_CLASSES
    rng = random.Random(seed)
    scene = None
    plate_iter = None
    for i in range(n):
        roll = rng.random()
        if roll < 0.1:
            if plate_iter is None:
                txt, prov = random_plate(rng)
                plate_iter = plate_scene_frames(rng.randint(0, 10**6), txt, prov)
            try:
                img, boxes = next(plate_iter)
                for _ in range(rng.randint(0, 6)):
                    img, boxes = next(plate_iter)
            except StopIteration:
                plate_iter = None
                continue
        else:
            if scene is None or rng.random() < 0.05:
                scene = build_scene(rng.randint(0, 10**6), duration=40,
                                    recipe=rng.choice(recipes) if recipes else "random",
                                    truck=rng.random() < 0.85, density=rng.uniform(*density))
            img, boxes = scene.render(rng.uniform(0, scene.duration), np.random.default_rng(rng.randint(0, 10**6)))
        labels = [(classes.index(c), *b) for c, b in boxes if c in classes]
        yield img, labels

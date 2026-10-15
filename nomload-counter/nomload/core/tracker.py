"""ByteTrack multi-object tracker (NumPy implementation).

Follows Zhang et al., "ByteTrack: Multi-Object Tracking by Associating Every
Detection Box" (ECCV 2022): high-score detections are matched to tracks
first, then the *low*-score leftovers are used to keep tracks alive through
occlusion (a bag partly hidden behind a labourer's arm still produces a weak
detection). A constant-velocity Kalman filter predicts motion between frames.

Tracking is class-group aware: countable goods only associate with goods,
people with people, so a labourer's box can never "steal" a bag's identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nomload.core.geometry import iou_matrix


# ----------------------------------------------------------------- assignment
def linear_assignment(cost: np.ndarray, thresh: float):
    """Minimum cost matching; pairs with cost > thresh are rejected."""
    if cost.size == 0:
        return [], list(range(cost.shape[0])), list(range(cost.shape[1]))
    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore
        r, c = linear_sum_assignment(cost)
        pairs = list(zip(r.tolist(), c.tolist()))
    except Exception:  # pragma: no cover - scipy is optional
        pairs = _hungarian(cost)
    matches = [(i, j) for i, j in pairs if cost[i, j] <= thresh]
    mi = {i for i, _ in matches}
    mj = {j for _, j in matches}
    return matches, [i for i in range(cost.shape[0]) if i not in mi], [j for j in range(cost.shape[1]) if j not in mj]


def _hungarian(cost: np.ndarray):
    """Classic O(n^3) Hungarian algorithm (Kuhn-Munkres) for rectangular matrices."""
    n, m = cost.shape
    transposed = False
    c = cost
    if n > m:
        c = cost.T
        n, m = m, n
        transposed = True
    big = float(np.max(c[np.isfinite(c)])) + 1 if np.isfinite(c).any() else 1.0
    c = np.where(np.isfinite(c), c, big * 10)
    u = np.zeros(n + 1)
    v = np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, np.inf)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = c[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = []
    for j in range(1, m + 1):
        if p[j] != 0:
            pairs.append((j - 1, p[j] - 1) if transposed else (p[j] - 1, j - 1))
    return pairs


# ----------------------------------------------------------------- kalman
class KalmanXYAH:
    """Constant velocity Kalman filter on (cx, cy, aspect, height)."""

    def __init__(self):
        self._motion = np.eye(8)
        for i in range(4):
            self._motion[i, 4 + i] = 1.0
        self._update = np.eye(4, 8)
        self._w_pos = 1.0 / 20
        self._w_vel = 1.0 / 160

    def initiate(self, z):
        mean = np.r_[z, np.zeros(4)]
        h = z[3]
        std = [2 * self._w_pos * h, 2 * self._w_pos * h, 1e-2, 2 * self._w_pos * h,
               10 * self._w_vel * h, 10 * self._w_vel * h, 1e-5, 10 * self._w_vel * h]
        return mean, np.diag(np.square(std))

    def predict(self, mean, cov):
        h = mean[3]
        std = [self._w_pos * h, self._w_pos * h, 1e-2, self._w_pos * h,
               self._w_vel * h, self._w_vel * h, 1e-5, self._w_vel * h]
        mean = self._motion @ mean
        cov = self._motion @ cov @ self._motion.T + np.diag(np.square(std))
        return mean, cov

    def update(self, mean, cov, z):
        h = mean[3]
        std = [self._w_pos * h, self._w_pos * h, 1e-1, self._w_pos * h]
        S = self._update @ cov @ self._update.T + np.diag(np.square(std))
        K = cov @ self._update.T @ np.linalg.inv(S)
        mean = mean + K @ (z - self._update @ mean)
        cov = cov - K @ S @ K.T
        return mean, cov


def xyxy_to_xyah(b):
    w, h = b[2] - b[0], b[3] - b[1]
    return np.array([b[0] + w / 2, b[1] + h / 2, w / max(h, 1e-3), max(h, 1e-3)])


def xyah_to_xyxy(m):
    cx, cy, a, h = m[:4]
    w = a * h
    return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])


# ----------------------------------------------------------------- tracks
_TRACKED, _LOST, _REMOVED = 0, 1, 2


@dataclass
class Track:
    track_id: int
    cls: str
    group: str
    mean: np.ndarray
    cov: np.ndarray
    score: float
    start_frame: int
    frame: int
    state: int = _TRACKED
    hits: int = 1
    scores: list = field(default_factory=list)
    cls_votes: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # (frame, cx, cy)
    last_box: np.ndarray | None = None
    activated: bool = False

    @property
    def box(self) -> np.ndarray:
        return xyah_to_xyxy(self.mean)

    @property
    def center(self) -> tuple[float, float]:
        return float(self.mean[0]), float(self.mean[1])

    @property
    def mean_score(self) -> float:
        return float(np.mean(self.scores[-15:])) if self.scores else self.score

    def vote(self, cls: str, score: float):
        self.cls_votes[cls] = self.cls_votes.get(cls, 0.0) + score
        self.cls = max(self.cls_votes.items(), key=lambda kv: kv[1])[0]


def class_group(cls: str, countable: set[str]) -> str:
    return "goods" if cls in countable else cls


class ByteTracker:
    def __init__(self, countable: set[str], high_thresh=0.45, low_thresh=0.15, new_thresh=0.5,
                 match_thresh=0.85, track_buffer=24, min_hits=2):
        self.countable = set(countable)
        self.high, self.low, self.new = high_thresh, low_thresh, new_thresh
        self.match_thresh = match_thresh
        self.buffer = track_buffer
        self.min_hits = min_hits
        self.kf = KalmanXYAH()
        self.tracks: list[Track] = []
        self.lost: list[Track] = []
        self.frame = 0
        self._next_id = 1
        self.removed_recent: list[Track] = []

    def reset(self):
        self.__init__(self.countable, self.high, self.low, self.new, self.match_thresh, self.buffer, self.min_hits)

    def _cost(self, tracks: list[Track], boxes: np.ndarray, classes: list[str]) -> np.ndarray:
        if not tracks or len(boxes) == 0:
            return np.zeros((len(tracks), len(boxes)), np.float32)
        tb = np.array([t.box for t in tracks])
        cost = 1.0 - iou_matrix(tb, boxes)
        # Centre-distance fallback for small fast items whose boxes barely overlap.
        tc = (tb[:, None, :2] + tb[:, None, 2:]) / 2
        dc = (boxes[None, :, :2] + boxes[None, :, 2:]) / 2
        dist = np.linalg.norm(tc - dc, axis=2)
        scale = np.maximum((tb[:, None, 3] - tb[:, None, 1]), 1.0)
        near = dist / scale
        cost = np.where((cost > 0.95) & (near < 0.9), 0.8 + near * 0.1, cost)
        for i, t in enumerate(tracks):
            for j, c in enumerate(classes):
                if class_group(c, self.countable) != t.group:
                    cost[i, j] = 9.0
        return cost

    def update(self, dets: list) -> list[Track]:
        """dets: list of Detection(x0,y0,x1,y1,score,cls). Returns confirmed active tracks."""
        self.frame += 1
        f = self.frame
        boxes = np.array([[d.x0, d.y0, d.x1, d.y1] for d in dets], np.float64).reshape(-1, 4)
        scores = np.array([d.score for d in dets])
        classes = [d.cls for d in dets]
        hi = [i for i in range(len(dets)) if scores[i] >= self.high]
        lo = [i for i in range(len(dets)) if self.low <= scores[i] < self.high]

        pool = self.tracks + self.lost
        for t in pool:
            if t.state != _TRACKED:
                t.mean[7] = 0  # freeze height velocity while lost
            t.mean, t.cov = self.kf.predict(t.mean, t.cov)

        # 1st association: all tracks vs high-score detections
        cost = self._cost(pool, boxes[hi], [classes[i] for i in hi])
        matches, u_trk, u_det = linear_assignment(cost, self.match_thresh)
        for ti, dj in matches:
            self._apply(pool[ti], dets[hi[dj]], f)
        remaining = [pool[i] for i in u_trk if pool[i].state == _TRACKED]
        unmatched_lost = [pool[i] for i in u_trk if pool[i].state != _TRACKED]
        # 2nd association: remaining tracked vs low-score detections
        cost2 = self._cost(remaining, boxes[lo], [classes[i] for i in lo])
        m2, u_trk2, _ = linear_assignment(cost2, 0.6)
        for ti, dj in m2:
            self._apply(remaining[ti], dets[lo[dj]], f)
        for i in u_trk2:
            t = remaining[i]
            t.state = _LOST
        # new tracks from unmatched high detections
        for dj in u_det:
            d = dets[hi[dj]]
            if d.score < self.new:
                continue
            b = boxes[hi[dj]]
            mean, cov = self.kf.initiate(xyxy_to_xyah(b))
            t = Track(self._next_id, d.cls, class_group(d.cls, self.countable), mean, cov, d.score, f, f)
            self._next_id += 1
            t.scores.append(d.score)
            t.vote(d.cls, d.score)
            t.history.append((f, *t.center))
            t.last_box = b
            t.activated = self.min_hits <= 1
            pool.append(t)
        # bookkeeping
        self.tracks = [t for t in pool if t.state == _TRACKED]
        self.lost = []
        self.removed_recent = [t for t in self.removed_recent if f - t.frame <= self.buffer * 2]
        for t in pool:
            if t.state == _LOST:
                if f - t.frame > self.buffer:
                    t.state = _REMOVED
                    self.removed_recent.append(t)
                else:
                    self.lost.append(t)
        del unmatched_lost
        return [t for t in self.tracks if t.activated]

    def _apply(self, t: Track, d, f: int):
        b = np.array([d.x0, d.y0, d.x1, d.y1], np.float64)
        t.mean, t.cov = self.kf.update(t.mean, t.cov, xyxy_to_xyah(b))
        t.state = _TRACKED
        t.frame = f
        t.hits += 1
        t.score = d.score
        t.scores.append(d.score)
        t.vote(d.cls, d.score)
        t.history.append((f, *t.center))
        if len(t.history) > 120:
            t.history = t.history[-120:]
        t.last_box = b
        if t.hits >= self.min_hits:
            t.activated = True

    @property
    def lost_tracks(self) -> list[Track]:
        return self.lost

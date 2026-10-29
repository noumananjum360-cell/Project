"""Camera tamper detection against a calibrated reference frame.

Detects: lens covered / camera blacked out, view blurred (spray, smeared lens,
defocus), camera moved (global shift of the scene) and large view change.
Moving people and trucks change parts of the image all the time, so every
check compares a slowly-updated background model (not the raw frame) and an
alert is only raised when a condition persists for ``persist_s`` seconds.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

SMALL = (160, 90)


@dataclass
class TamperResult:
    status: str        # ok|covered|blurred|moved|changed
    detail: str
    metrics: dict


def _prep(frame: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv2.resize(g, SMALL, interpolation=cv2.INTER_AREA).astype(np.float32)


def _sharpness(g: np.ndarray) -> float:
    return float(cv2.Laplacian(g, cv2.CV_32F).var())


def _edges(g: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


class TamperDetector:
    def __init__(self, reference: np.ndarray | None = None, persist_s: float = 4.0,
                 blur_ratio: float = 0.25, shift_frac: float = 0.06, change_thresh: float = 0.45):
        self.persist_s = persist_s
        self.blur_ratio = blur_ratio
        self.shift_frac = shift_frac
        self.change_thresh = change_thresh
        self.ref = None
        self.bg = None
        self._since: dict[str, float] = {}
        self._raised: str = "ok"
        if reference is not None:
            self.set_reference(reference)

    def set_reference(self, frame: np.ndarray):
        self.ref = _prep(frame)
        self.ref_sharp = max(_sharpness(self.ref), 1e-3)
        self.ref_edges = _edges(self.ref)
        self.bg = self.ref.copy()

    def evaluate(self, frame: np.ndarray) -> TamperResult:
        g = _prep(frame)
        if self.bg is None:
            self.set_reference(frame)
        cv2.accumulateWeighted(g, self.bg, 0.05)
        bg = self.bg
        m = {"mean": float(g.mean()), "std": float(g.std())}
        if m["mean"] < 22 or m["std"] < 7:
            return TamperResult("covered", "Camera view is dark or covered", m)
        sharp = _sharpness(bg)
        m["sharp_ratio"] = sharp / self.ref_sharp
        if m["sharp_ratio"] < self.blur_ratio:
            return TamperResult("blurred", "Camera view is blurred or smeared", m)
        (dx, dy), resp = cv2.phaseCorrelate(self.ref, bg)
        m["shift"] = float(np.hypot(dx / SMALL[0], dy / SMALL[1]))
        m["resp"] = float(resp)
        if m["shift"] > self.shift_frac and resp > 0.05:
            return TamperResult("moved", "Camera has been moved from its calibrated position", m)
        e = _edges(bg)
        a, b = e.flatten(), self.ref_edges.flatten()
        corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
        m["edge_corr"] = corr
        if corr < self.change_thresh:
            return TamperResult("changed", "Camera view differs significantly from calibration", m)
        return TamperResult("ok", "", m)

    def update(self, frame: np.ndarray, now: float | None = None) -> TamperResult | None:
        """Returns a result only when a tamper state has persisted (edge triggered)."""
        now = time.time() if now is None else now
        r = self.evaluate(frame)
        if r.status == "ok":
            self._since.clear()
            if self._raised != "ok":
                self._raised = "ok"
                return r  # recovered
            return None
        t0 = self._since.setdefault(r.status, now)
        for k in list(self._since):
            if k != r.status:
                del self._since[k]
        if now - t0 >= self.persist_s and self._raised != r.status:
            self._raised = r.status
            return r
        return None

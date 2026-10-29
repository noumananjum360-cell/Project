"""Evidence recording: rolling pre-roll buffer, session clips and snapshots."""
from __future__ import annotations

import collections
import threading
import time
from pathlib import Path

import cv2
import numpy as np


class RollingBuffer:
    """Keeps the last N seconds of JPEG-compressed frames (cheap on RAM)."""

    def __init__(self, seconds: float = 20.0, fps: float = 8.0, quality: int = 80):
        self.seconds = seconds
        self.fps = fps
        self.quality = quality
        self._buf: collections.deque = collections.deque()
        self._last = 0.0
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, ts: float | None = None):
        ts = time.time() if ts is None else ts
        if ts - self._last < 1.0 / self.fps:
            return
        self._last = ts
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            return
        with self._lock:
            self._buf.append((ts, jpg))
            while self._buf and ts - self._buf[0][0] > self.seconds:
                self._buf.popleft()

    def frames(self):
        with self._lock:
            items = list(self._buf)
        for ts, jpg in items:
            yield ts, cv2.imdecode(jpg, cv2.IMREAD_COLOR)

    def clear(self):
        with self._lock:
            self._buf.clear()


class ClipRecorder:
    """Writes the loading clip for one session (pre-roll + live) to MP4."""

    def __init__(self, path: Path, fps: float = 8.0, max_width: int = 960):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.max_width = max_width
        self._vw = None
        self._size = None
        self._last = 0.0
        self.frames = 0
        self._lock = threading.Lock()

    def _ensure(self, frame):
        if self._vw is None:
            h, w = frame.shape[:2]
            if w > self.max_width:
                h = int(h * self.max_width / w) // 2 * 2
                w = self.max_width
            self._size = (w, h)
            self._vw = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))

    def write(self, frame: np.ndarray, ts: float | None = None, force: bool = False):
        ts = time.time() if ts is None else ts
        if not force and ts - self._last < 1.0 / self.fps:
            return
        self._last = ts
        with self._lock:
            self._ensure(frame)
            if frame.shape[1] != self._size[0] or frame.shape[0] != self._size[1]:
                frame = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)
            self._vw.write(frame)
            self.frames += 1

    def write_buffer(self, buf: RollingBuffer):
        for ts, fr in buf.frames():
            self.write(fr, ts, force=True)

    def close(self) -> Path | None:
        with self._lock:
            if self._vw is not None:
                self._vw.release()
                self._vw = None
        return self.path if self.path.exists() and self.frames else None


def stamp(frame: np.ndarray, text: str) -> np.ndarray:
    """Burn a timestamp/caption into an evidence image."""
    out = frame.copy()
    h, w = out.shape[:2]
    cv2.rectangle(out, (0, h - 22), (w, h), (20, 20, 20), -1)
    cv2.putText(out, text, (6, h - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def snapshot(frame: np.ndarray, box, path: Path, caption: str = "", thumb_width: int = 320) -> Path:
    """Save a thumbnail of the whole frame with the counted item highlighted."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = frame.copy()
    x0, y0, x1, y1 = [int(v) for v in box]
    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 200, 255), 3)
    h, w = img.shape[:2]
    if w > thumb_width:
        img = cv2.resize(img, (thumb_width, int(h * thumb_width / w)), interpolation=cv2.INTER_AREA)
    if caption:
        img = stamp(img, caption)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return path

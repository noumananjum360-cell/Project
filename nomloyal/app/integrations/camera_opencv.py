"""OpenCV camera: USB webcam (index) or RTSP stream, read in a background thread with automatic reconnection.
Frames are kept in memory only (never written to disk)."""
from __future__ import annotations

import logging
import os
import threading
import time

from app.integrations.camera_base import CameraSource, CameraStatus

log = logging.getLogger(__name__)


def mask_url(url: str) -> str:
    """rtsp://user:pass@host -> rtsp://user:***@host (for logs and the screen)."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        cred, host = rest.split("@", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def open_capture(kind: str, source: str):
    import cv2
    if kind == "usb":
        idx = int(source or 0)
        return cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    return cap


def discover_usb(max_index: int = 4) -> list[int]:
    """Indexes of USB cameras that open (slow on some PCs - call from a background thread)."""
    found = []
    for i in range(max_index):
        cap = open_capture("usb", str(i))
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            found.append(i)
    return found


def test_camera(kind: str, source: str, timeout: float = 8.0) -> tuple[bool, str, object]:
    """(ok, message, frame) - opens the camera once and reads one frame."""
    result = {"ok": False, "msg": "No answer from the camera (timeout).", "frame": None}

    def run():
        try:
            cap = open_capture(kind, source)
            if not cap.isOpened():
                result["msg"] = "Cannot open the camera. Check the index / URL, user and password."
                return
            ok, fr = cap.read()
            cap.release()
            if ok and fr is not None:
                result.update(ok=True, msg=f"Connected: {fr.shape[1]}x{fr.shape[0]}", frame=fr)
            else:
                result["msg"] = "The camera opened but sent no picture."
        except Exception as exc:  # noqa: BLE001
            result["msg"] = f"Camera error: {exc}"
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    return result["ok"], result["msg"], result["frame"]


class OpenCVCamera(CameraSource):
    def __init__(self, kind: str, source: str, fps: float = 10, max_width: int = 960):
        self.kind, self.source = kind, source
        self.period = 1.0 / max(1.0, float(fps))
        self.max_width = max_width
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = CameraStatus()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._status = CameraStatus(True, False, 0.0, "Connecting...")
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._status = CameraStatus(False, False, 0.0, "Stopped")
        with self._lock:
            self._frame = None

    def latest(self):
        with self._lock:
            return self._frame

    def status(self) -> CameraStatus:
        return self._status

    def _run(self):
        import cv2
        backoff = 1.0
        while not self._stop.is_set():
            cap = open_capture(self.kind, self.source)
            if not cap.isOpened():
                self._status = CameraStatus(True, False, 0.0, f"Cannot connect - retrying in {int(backoff)} s")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff, fails, n, t0 = 1.0, 0, 0, time.time()
            while not self._stop.is_set():
                ok, fr = cap.read()
                if not ok or fr is None:
                    fails += 1
                    if fails > 25:
                        break
                    time.sleep(0.05)
                    continue
                fails = 0
                if fr.shape[1] > self.max_width:
                    h = int(fr.shape[0] * self.max_width / fr.shape[1])
                    fr = cv2.resize(fr, (self.max_width, h), interpolation=cv2.INTER_AREA)
                with self._lock:
                    self._frame = fr
                n += 1
                el = time.time() - t0
                if el >= 2:
                    self._status = CameraStatus(True, True, n / el, "Live")
                    n, t0 = 0, time.time()
                elif not self._status.connected:
                    self._status = CameraStatus(True, True, 0.0, "Live")
                self._stop.wait(self.period)
            cap.release()
            if not self._stop.is_set():
                self._status = CameraStatus(True, False, 0.0, "Connection lost - reconnecting")
                self._stop.wait(backoff)

"""Video sources: RTSP IP cameras, USB webcams and video files.

Each source runs its own reader thread that always keeps only the *latest*
frame (older frames are dropped), so a slow PC never builds up latency. Lost
streams are reconnected automatically with back-off; ``offline_for()`` lets the
pipeline raise a "camera offline" alert after a configurable time.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Prefer TCP for RTSP: far fewer smeared/grey frames on busy factory networks.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

BRANDS = {
    "Hikvision": "rtsp://{auth}{ip}:{port}/Streaming/Channels/{channel}0{stream}",
    "Dahua": "rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={channel}&subtype={substream}",
    "CP Plus": "rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={channel}&subtype={substream}",
    "Uniview": "rtsp://{auth}{ip}:{port}/unicast/c{channel}/s{substream}/live",
    "TP-Link Tapo/VIGI": "rtsp://{auth}{ip}:{port}/stream{stream}",
    "Generic ONVIF": "rtsp://{auth}{ip}:{port}/onvif1",
    "Generic (H.264)": "rtsp://{auth}{ip}:{port}/h264",
}
GENERIC_PATHS = ["/onvif1", "/live", "/h264", "/stream1", "/Streaming/Channels/101",
                 "/cam/realmonitor?channel=1&subtype=0", "/live/ch00_0", "/11", "/media/video1"]


def rtsp_url(brand: str, ip: str, user: str = "", password: str = "", port: int = 554,
             channel: int = 1, substream: bool = False) -> str:
    """Build an RTSP URL for common camera / NVR brands sold in Pakistan."""
    auth = ""
    if user:
        auth = quote(user, safe="") + (":" + quote(password, safe="") if password else "") + "@"
    tpl = BRANDS.get(brand, BRANDS["Generic ONVIF"])
    return tpl.format(auth=auth, ip=ip.strip(), port=port, channel=channel,
                      stream=2 if substream else 1, substream=1 if substream else 0)


def mask_url(url: str) -> str:
    """Hide the password in an RTSP URL for logs and UI."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        cred, host = rest.split("@", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}://{user}:****@{host}"
    return url


@dataclass
class SourceSpec:
    kind: str          # rtsp | usb | file
    uri: str           # url, device index or path
    loop: bool = True  # loop video files
    realtime: bool = True  # pace files at their native fps

    def open(self) -> cv2.VideoCapture:
        if self.kind == "usb":
            idx = int(self.uri or 0)
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
        elif self.kind == "rtsp":
            cap = cv2.VideoCapture(self.uri, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        else:
            cap = cv2.VideoCapture(str(self.uri))
        return cap

    @classmethod
    def from_dict(cls, d: dict) -> "SourceSpec":
        return cls(d.get("kind", "file"), str(d.get("uri", "")), bool(d.get("loop", True)),
                   bool(d.get("realtime", True)))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "uri": self.uri, "loop": self.loop, "realtime": self.realtime}


def test_connection(spec: SourceSpec, timeout: float = 8.0) -> tuple[bool, np.ndarray | None, str]:
    """Try to grab one frame. Returns (ok, frame, message)."""
    result: dict = {}

    def run():
        try:
            cap = spec.open()
            if not cap.isOpened():
                result["msg"] = "Could not open the stream. Check IP address, port, username and password."
                return
            t0 = time.time()
            while time.time() - t0 < timeout:
                ok, fr = cap.read()
                if ok and fr is not None:
                    h, w = fr.shape[:2]
                    fps = cap.get(cv2.CAP_PROP_FPS) or 0
                    result.update(ok=True, frame=fr, msg=f"Connected: {w}x{h} @ {fps:.0f} fps")
                    break
            else:
                result["msg"] = "Stream opened but no video frames were received."
            cap.release()
        except Exception as e:  # pragma: no cover
            result["msg"] = f"Error: {e}"

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout + 4)
    if th.is_alive():
        return False, None, "Timed out. The camera did not respond."
    return bool(result.get("ok")), result.get("frame"), result.get("msg", "Unknown error")


class VideoSource(threading.Thread):
    """Background reader that exposes the most recent frame."""

    def __init__(self, spec: SourceSpec, name: str = "camera"):
        super().__init__(daemon=True, name=f"src-{name}")
        self.spec = spec
        self.cam_name = name
        self._frame: np.ndarray | None = None
        self._frame_id = 0
        self._ts = 0.0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = threading.Event()
        self.online = False
        self.offline_since: float | None = time.time()
        self.fps = 15.0
        self.frames_read = 0
        self.ended = False      # a non-looping file finished
        self.last_error = ""
        self._consumed = 0
        # Offline analysis of a file: deliver every frame (wait for the consumer).
        self.lockstep = spec.kind == "file" and not spec.realtime

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    def offline_for(self) -> float:
        since = self.offline_since  # read once: the reader thread may change it concurrently
        if self.online or since is None:
            return 0.0
        return time.time() - since

    def read(self, last_id: int = -1, timeout: float = 1.0):
        """Wait for a frame newer than ``last_id``. Returns (frame_id, ts, frame) or None."""
        with self._cond:
            if self._frame_id == last_id:
                self._cond.wait(timeout)
            if self._frame is None or self._frame_id == last_id:
                return None
            self._consumed = self._frame_id
            self._cond.notify_all()
            return self._frame_id, self._ts, self._frame

    def run(self):
        backoff = 1.0
        while not self._stop.is_set():
            cap = self.spec.open()
            if not cap.isOpened():
                self._mark_offline(f"cannot open {mask_url(self.spec.uri)}")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 15.0)
                continue
            fps = cap.get(cv2.CAP_PROP_FPS)
            self.fps = fps if fps and 1 <= fps <= 120 else 15.0
            backoff = 1.0
            period = 1.0 / self.fps
            next_t = time.time()
            fails = 0
            while not self._stop.is_set():
                ok, fr = cap.read()
                if not ok or fr is None:
                    if self.spec.kind == "file":
                        if self.spec.loop:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ok, fr = cap.read()
                            if not ok:
                                break
                        else:
                            if self.lockstep:  # let the consumer take the last frame first
                                with self._cond:
                                    while self._consumed < self._frame_id and not self._stop.is_set():
                                        self._cond.wait(0.5)
                            self.ended = True
                            self._mark_offline("end of file")
                            cap.release()
                            return
                    else:
                        fails += 1
                        if fails > 25:
                            break
                        time.sleep(0.02)
                        continue
                fails = 0
                with self._cond:
                    if self.lockstep:
                        while self._consumed < self._frame_id and not self._stop.is_set():
                            self._cond.wait(0.5)
                    self._frame = fr
                    self._frame_id += 1
                    self._ts = time.time()
                    self._cond.notify_all()
                self.frames_read += 1
                if not self.online:
                    self.online = True
                    self.offline_since = None
                    log.info("Camera %s online", self.cam_name)
                if self.spec.kind == "file" and self.spec.realtime:
                    next_t += period
                    d = next_t - time.time()
                    if d > 0:
                        time.sleep(d)
                    else:
                        next_t = time.time()
            cap.release()
            if not self._stop.is_set():
                self._mark_offline("stream lost - reconnecting")
                self._stop.wait(backoff)

    def _mark_offline(self, reason: str):
        self.last_error = reason
        if self.online or self.offline_since is None:
            self.offline_since = time.time()
        self.online = False
        log.warning("Camera %s offline: %s", self.cam_name, reason)


def list_usb_cameras(max_index: int = 4) -> list[int]:
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found

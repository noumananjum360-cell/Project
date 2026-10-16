"""Per-bay runtime thread: cameras -> counting engine -> sessions/evidence/alerts.

The UI never calls OpenCV or ONNX directly. Each bay runs in its own thread and
reports to a listener (the Qt bridge turns these calls into signals).
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2

from nomload.core.pipeline import CountingEngine, EngineConfig
from nomload.core.plates import PlateReader
from nomload.core.recorder import ClipRecorder, RollingBuffer, snapshot
from nomload.core.tamper import TamperDetector
from nomload.core.video import VideoSource
from nomload.services import evidence
from nomload.services.bays import Bay
from nomload.services.context import User

log = logging.getLogger(__name__)


class RuntimeListener:
    """Override what you need. Called from the bay thread."""

    def frame(self, bay_id: int, frame, status: dict): ...
    def count(self, bay_id: int, event: dict): ...
    def session_changed(self, bay_id: int, session_id: int | None): ...
    def plate(self, bay_id: int, text: str, confidence: float, image_path: str | None): ...
    def prompt(self, bay_id: int, kind: str, data: dict): ...


class BayRuntime(threading.Thread):
    def __init__(self, app, bay: Bay, listener: RuntimeListener | None = None):
        super().__init__(daemon=True, name=f"bay-{bay.id}")
        self.app = app
        self.bay = bay
        self.listener = listener or RuntimeListener()
        s = app.settings
        cam = bay.count_camera
        self.cam = cam
        self.engine = CountingEngine(app.registry, cam.geometry if cam else None,
                                     EngineConfig(max_width=int(s.get("max_process_width") or 960),
                                                  review_threshold=float(s.get("review_threshold") or 0.45)))
        self.src = VideoSource(cam.source, f"{bay.name}/{cam.name}") if cam else None
        pc = bay.plate_camera
        self.plate_cam = pc
        self.plate_src = VideoSource(pc.source, f"{bay.name}/{pc.name}") if pc else None
        self.tamper = TamperDetector(cam.reference, persist_s=float(s.get("tamper_persist_s") or 5)) \
            if cam is not None and cam.reference is not None and s.get("tamper_enabled") else None
        self.buffer = RollingBuffer(float(s.get("preroll_s") or 15), float(s.get("clip_fps") or 8))
        self.plates = PlateReader(app.ocr)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.session_id: int | None = app.sessions.active_for_bay(bay.id)
        self.session_started_at = time.time()
        self.recorder: ClipRecorder | None = None
        self.plate_locked = False
        self.active_product_id: int | None = None
        self.truck_present = False
        self._truck_since: float | None = None
        self._truck_seen_in_session = False
        self.status = {"online": False, "fps": 0.0, "infer_ms": 0.0, "tamper": "ok", "message": "Starting..."}
        self._offline_alerted = False
        self._last_tamper_check = 0.0
        self._last_emit = 0.0
        self._event_seq = 0
        self.skip = int(s.get("frame_skip") or 0)
        if self.session_id:
            self._resume_session()

    # ------------------------------------------------------------------ control
    def stop(self):
        self._stop.set()

    def shutdown(self):
        self.stop()
        for s in (self.src, self.plate_src):
            if s:
                s.stop()
        with self._lock:
            rec, self.recorder = self.recorder, None
            if rec:
                rec.close()

    def _resume_session(self):
        """App restarted during a session: continue counting into the same session."""
        sid = self.session_id
        s = self.app.sessions.summary(sid)
        self.session_started_at = s.started_at
        d = evidence.session_dir(sid, s.started_at)
        n = len(list(d.glob("clip*.mp4")))
        self.recorder = ClipRecorder(d / (f"clip_{n}.mp4" if n else "clip.mp4"), float(self.app.settings.get("clip_fps") or 8))
        self.plate_locked = bool(s.plate_text)

    def start_session(self, user: User | None, gate_pass_id: int | None = None, auto: bool = False) -> int:
        with self._lock:
            sid = self.app.sessions.start(self.bay.id, user, gate_pass_id, auto)
            self.session_id = sid
            self.session_started_at = time.time()
            self.engine.reset_counts()
            self.plates.reset()
            self.plate_locked = False
            self._truck_seen_in_session = self.truck_present
            self._event_seq = 0
            d = evidence.session_dir(sid)
            self.recorder = ClipRecorder(d / "clip.mp4", float(self.app.settings.get("clip_fps") or 8))
            self.recorder.write_buffer(self.buffer)
            if gate_pass_id:
                gp = self.app.gate_passes.get(gate_pass_id)
                if gp and len(gp.items) >= 1:
                    self.active_product_id = gp.items[0].product_id
        self.listener.session_changed(self.bay.id, sid)
        return sid

    def close_session(self, user: User | None):
        with self._lock:
            sid = self.session_id
            if not sid:
                return None
            summary = self.app.sessions.close(sid, user)
            self._finalise_evidence(sid)
            self.session_id = None
            self.recorder = None
        if summary.status == "mismatch":
            diffs = ", ".join(f"{l.name} {l.counted}/{l.expected if l.expected is not None else '?'}"
                              for l in summary.lines if not l.ok) or "no gate pass linked"
            self.app.alerts.raise_alert("mismatch", f"{self.bay.name}: truck {summary.plate_text or '-'} "
                                        f"(GP {summary.gate_pass.number if summary.gate_pass else '-'}) mismatch: {diffs}",
                                        self.bay.id, sid)
        self.listener.session_changed(self.bay.id, None)
        return summary

    def cancel_session(self, user: User, reason: str):
        with self._lock:
            sid = self.session_id
            if not sid:
                return
            self.app.sessions.cancel(sid, user, reason)
            self._finalise_evidence(sid)
            self.session_id = None
            self.recorder = None
        self.listener.session_changed(self.bay.id, None)

    def _finalise_evidence(self, sid: int):
        if self.recorder:
            p = self.recorder.close()
            if p:
                evidence.register(self.app.db, sid, "clip", p)
                self.app.sessions.set_clip(sid, str(p))

    def set_plate_manual(self, text: str, user: User):
        if self.session_id:
            self.app.sessions.set_plate(self.session_id, text, 1.0, None, user, corrected=True)
            self.plate_locked = True
            self.listener.plate(self.bay.id, text, 1.0, None)

    def update_geometry(self, geometry, reference=None):
        self.engine.set_geometry(geometry)
        if reference is not None and self.app.settings.get("tamper_enabled"):
            self.tamper = TamperDetector(reference, persist_s=float(self.app.settings.get("tamper_persist_s") or 5))

    # ------------------------------------------------------------------ loop
    def run(self):
        try:
            self._run()
        except Exception:
            log.exception("bay %s runtime crashed", self.bay.name)
            self.status.update(online=False, message="Processing error - see log")
            self.listener.frame(self.bay.id, None, dict(self.status))
            for s in (self.src, self.plate_src):
                if s:
                    s.stop()

    def _run(self):
        if self.src is None:
            self.status["message"] = "No counting camera configured for this bay"
            self.listener.frame(self.bay.id, None, dict(self.status))
            return
        self.src.start()
        if self.plate_src:
            self.plate_src.start()
        last_id = -1
        n = 0
        t_fps = time.time()
        frames_fps = 0
        while not self._stop.is_set():
            got = self.src.read(last_id, 0.5)
            if got is None:
                self._check_offline()
                if time.time() - self._last_emit > 1.0:
                    self.status.update(online=self.src.online, message=self.src.last_error or "Waiting for video...")
                    self.listener.frame(self.bay.id, None, dict(self.status))
                    self._last_emit = time.time()
                continue
            last_id, ts, frame = got
            self._check_offline()
            n += 1
            if self.skip and n % (self.skip + 1):
                continue
            try:
                self._process(frame, ts, n)
            except Exception:
                log.exception("bay %s processing error", self.bay.name)
                time.sleep(0.2)
            frames_fps += 1
            if time.time() - t_fps >= 2.0:
                self.status["fps"] = frames_fps / (time.time() - t_fps)
                frames_fps, t_fps = 0, time.time()
        for s in (self.src, self.plate_src):
            if s:
                s.stop()

    def _check_offline(self):
        lim = float(self.app.settings.get("camera_offline_alert_s") or 30)
        off = self.src.offline_for()
        if off > lim and not self._offline_alerted:
            self._offline_alerted = True
            self.app.alerts.raise_alert("camera_offline", f"{self.bay.name}: camera '{self.cam.name}' offline for "
                                        f"{int(off)} s ({self.src.last_error})", self.bay.id, self.session_id)
        elif self.src.online and self._offline_alerted:
            self._offline_alerted = False
            self.app.alerts.raise_alert("camera_online", f"{self.bay.name}: camera '{self.cam.name}' is back online",
                                        self.bay.id, self.session_id)

    def _process(self, frame, ts, n):
        res = self.engine.process(frame, ts)
        self.status.update(online=True, infer_ms=res.infer_ms, message="", truck=self.truck_present)
        # ---- tamper
        if self.tamper and ts - self._last_tamper_check > 1.0:
            self._last_tamper_check = ts
            tr = self.tamper.update(res.frame, ts)
            if tr is not None:
                self.status["tamper"] = tr.status
                if tr.status != "ok":
                    self.app.alerts.raise_alert("tamper", f"{self.bay.name}: {tr.detail}", self.bay.id, self.session_id)
        # ---- truck presence
        self._truck_logic(res.truck_present, ts)
        self.status["truck"] = self.truck_present
        # ---- counts
        with self._lock:
            sid = self.session_id
            for ev in res.events:
                if sid:
                    self._record_event(sid, ev, res.frame)
                else:
                    self.listener.count(self.bay.id, {"session_id": None, "cls": ev.cls, "direction": ev.direction,
                                                      "confidence": ev.confidence, "flagged": ev.flagged,
                                                      "product": None, "units": 1})
            annotated = self.engine.annotate(res)
            self.buffer.push(annotated, ts)
            if self.recorder:
                self.recorder.write(annotated, ts)
        # ---- plate
        if sid and not self.plate_locked and n % 4 == 0 and self.app.settings.get("auto_plate_read"):
            self._plate_logic(res)
        if ts - self._last_emit >= 1 / 15:
            self._last_emit = ts
            self.listener.frame(self.bay.id, annotated, dict(self.status))

    def _record_event(self, sid, ev, frame):
        self._event_seq += 1
        d = evidence.session_dir(sid, self.session_started_at) / "snapshots"
        sign = "+1" if ev.direction > 0 else "-1"
        path = d / f"{self._event_seq:05d}_{ev.cls}_{'in' if ev.direction > 0 else 'out'}.jpg"
        caption = f"{time.strftime('%d-%m-%Y %H:%M:%S', time.localtime(ev.timestamp))}  {ev.cls} {sign}  " \
                  f"conf {ev.confidence:.2f}  track {ev.track_id}"
        snapshot(frame, ev.box, path, caption)
        evidence.register(self.app.db, sid, "snapshot", path)
        eid, product = self.app.sessions.add_event(sid, ev.cls, ev.direction, ev.confidence, ev.flagged, ev.reason,
                                                   ev.track_id, str(path), list(ev.box), self.active_product_id,
                                                   ev.timestamp)
        if ev.flagged:
            self.app.alerts.raise_alert("low_confidence", f"{self.bay.name}: {ev.cls} {sign} needs review "
                                        f"({ev.reason}, confidence {ev.confidence:.0%})", self.bay.id, sid)
        self.listener.count(self.bay.id, {"session_id": sid, "event_id": eid, "cls": ev.cls, "direction": ev.direction,
                                          "confidence": ev.confidence, "flagged": ev.flagged,
                                          "product": product.name if product else None,
                                          "units": product.units_per_detection if product else 1,
                                          "snapshot": str(path)})

    def _truck_logic(self, present: bool, ts: float):
        s = self.app.settings
        if present:
            self._truck_since = self._truck_since or ts
            if self.session_id:
                self._truck_seen_in_session = True
        else:
            self._truck_since = None
        was = self.truck_present
        self.truck_present = present or (ts - self.engine.last_truck_seen < 3.0)
        if self.truck_present != was:
            self.listener.prompt(self.bay.id, "truck", {"present": self.truck_present})
        start_s = float(s.get("truck_present_start_s") or 5)
        if (self.bay.auto_session and not self.session_id and self._truck_since and ts - self._truck_since >= start_s):
            try:
                sid = self.start_session(None, None, auto=True)
                self.listener.prompt(self.bay.id, "auto_started", {"session_id": sid})
            except Exception as e:  # already running etc.
                log.info("auto start skipped: %s", e)
            self._truck_since = None
        absent_s = float(s.get("truck_absent_close_s") or 45)
        if (self.session_id and self._truck_seen_in_session and self.engine.last_truck_seen
                and ts - self.engine.last_truck_seen > absent_s):
            self._truck_seen_in_session = False
            self.listener.prompt(self.bay.id, "truck_left", {"session_id": self.session_id})

    def _plate_logic(self, res):
        frame = None
        roi = None
        dets = None
        if self.plate_src:
            got = self.plate_src.read(-2, 0.0)
            if got:
                frame = self.engine.prepare(got[2])
                g = self.plate_cam.geometry.to_pixels(frame.shape[1], frame.shape[0])
                roi = g.plate_roi
        else:
            frame = res.frame
            roi = self.engine._pix.plate_roi if self.engine._pix else None
            dets = res.plates
        if frame is None:
            return
        if self.plate_src:
            det = self.app.registry.detector
            dets = [d for d in det.detect(frame) if d.cls == "plate"] if det and "plate" in det.classes else None
        read = self.plates.read_frame(frame, roi, dets)
        self.plates.add(read)
        if self.plates.confident():
            best = self.plates.best()
            sid = self.session_id
            path = evidence.session_dir(sid, self.session_started_at) / "plate.jpg"
            cv2.imwrite(str(path), best.crop)
            evidence.register(self.app.db, sid, "plate", path)
            self.app.sessions.set_plate(sid, best.text, best.confidence, str(path))
            self.plate_locked = True
            self.listener.plate(self.bay.id, best.text, best.confidence, str(path))
            self._match_gate_pass(sid, best.text)

    def _match_gate_pass(self, sid: int, plate: str):
        s = self.app.sessions.summary(sid)
        from nomload.core.plate_formats import plates_match
        if s.gate_pass is None:
            gp = self.app.gate_passes.match_plate(plate)
            if gp:
                self.listener.prompt(self.bay.id, "gate_pass_match", {"session_id": sid, "gate_pass_id": gp.id,
                                                                      "number": gp.number, "plate": plate})
        elif s.gate_pass.vehicle_no and not plates_match(s.gate_pass.vehicle_no, plate, 1):
            self.app.alerts.raise_alert("plate_mismatch", f"{self.bay.name}: plate {plate} does not match gate pass "
                                        f"{s.gate_pass.number} vehicle {s.gate_pass.vehicle_no}", self.bay.id, sid)

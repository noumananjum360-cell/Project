"""ONNX Runtime object detectors.

Two model formats are supported, both plain ONNX files:

* ``nomload-centernet`` - the built-in lightweight detector (starter model and
  models fine-tuned with the built-in trainer). Output: per-class heatmaps
  plus log-size maps at stride 4.
* ``yolo`` - YOLOv5/v8/v11 detectors exported by Ultralytics
  (``yolo export format=onnx``). Output ``[1, 4+nc, N]`` (v8/v11) or
  ``[1, N, 5+nc]`` (v5). Class names come from the ``names`` metadata.

Execution providers: CPU by default; DirectML (Windows GPU, any vendor) when
enabled in settings and ``onnxruntime-directml`` is installed; CUDA if present.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Detection:
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def box(self):
        return (self.x0, self.y0, self.x1, self.y1)


def available_providers() -> list[str]:
    import onnxruntime as ort
    return ort.get_available_providers()


def choose_providers(use_gpu: bool) -> list[str]:
    avail = available_providers()
    order = []
    if use_gpu:
        for p in ("DmlExecutionProvider", "CUDAExecutionProvider"):
            if p in avail:
                order.append(p)
    order.append("CPUExecutionProvider")
    return order


def max_threads() -> int:
    """Never more AI threads than cores, and always one core left for the window."""
    return max(1, (os.cpu_count() or 2) - 1)


def default_threads() -> int:
    n = os.cpu_count() or 2
    return max(1, min(4, n // 2))


class OnnxDetector:
    def __init__(self, path: str | Path, use_gpu: bool = False, threads: int = 0,
                 conf_threshold: float = 0.3, class_thresholds: dict | None = None):
        import onnxruntime as ort
        self.path = str(path)
        so = ort.SessionOptions()
        # Leave cores for the window and the cameras: by default ONNX Runtime takes every
        # core and busy-spins between frames, which starves the UI ("Not responding").
        so.intra_op_num_threads = min(int(threads), max_threads()) if threads else default_threads()
        so.inter_op_num_threads = 1
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        so.add_session_config_entry("session.inter_op.allow_spinning", "0")
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.providers = choose_providers(use_gpu)
        self.session = ort.InferenceSession(self.path, so, providers=self.providers)
        meta = self.session.get_modelmeta().custom_metadata_map
        self.meta = dict(meta)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.format = meta.get("format", "")
        if not self.format:
            self.format = "yolo"
        if self.format == "nomload-centernet":
            self.classes = json.loads(meta["classes"])
            self.input_hw = tuple(json.loads(meta.get("input_hw", "[192, 320]")))
            self.stride = int(meta.get("stride", "4"))
        else:
            names = meta.get("names")
            if names:
                try:
                    d = ast.literal_eval(names)
                    self.classes = [d[k] for k in sorted(d)] if isinstance(d, dict) else list(d)
                except Exception:
                    self.classes = [s.strip() for s in names.split(",")]
            else:
                self.classes = [f"class{i}" for i in range(80)]
            shp = inp.shape
            h = shp[2] if isinstance(shp[2], int) else 640
            w = shp[3] if isinstance(shp[3], int) else 640
            self.input_hw = (h, w)
        self.conf = conf_threshold
        self.class_thr = class_thresholds or {}
        self.name = meta.get("name", Path(self.path).stem)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ api
    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        if self.format == "nomload-centernet":
            return self._detect_centernet(frame_bgr)
        return self._detect_yolo(frame_bgr)

    def info(self) -> dict:
        return {"path": self.path, "format": self.format, "classes": self.classes,
                "input": list(self.input_hw), "providers": self.providers, "name": self.name}

    # ------------------------------------------------------------------ centernet
    def _detect_centernet(self, frame):
        h, w = self.input_hw
        fh, fw = frame.shape[:2]
        x = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
        x = x.transpose(2, 0, 1)[None]
        out = self.session.run(None, {self.input_name: np.ascontiguousarray(x)})[0][0]
        return decode_centernet(out, self.classes, self.stride, fw / w, fh / h, self.conf, self.class_thr)

    # ------------------------------------------------------------------ yolo
    def _detect_yolo(self, frame):
        h, w = self.input_hw
        fh, fw = frame.shape[:2]
        r = min(w / fw, h / fh)
        nw, nh = int(round(fw * r)), int(round(fh * r))
        img = np.full((h, w, 3), 114, np.uint8)
        dx, dy = (w - nw) // 2, (h - nh) // 2
        img[dy:dy + nh, dx:dx + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.session.run(None, {self.input_name: np.ascontiguousarray(x)})[0]
        out = out[0]
        nc = len(self.classes)
        if out.shape[0] == 4 + nc:          # v8 / v11: [4+nc, N]
            out = out.T
            boxes, cls_scores = out[:, :4], out[:, 4:]
        elif out.shape[-1] == 5 + nc:       # v5: [N, 5+nc]
            boxes, cls_scores = out[:, :4], out[:, 5:] * out[:, 4:5]
        else:                               # unknown head - assume v8 layout
            out = out.T if out.shape[0] < out.shape[1] else out
            boxes, cls_scores = out[:, :4], out[:, 4:]
            nc = cls_scores.shape[1]
            if len(self.classes) < nc:
                self.classes += [f"class{i}" for i in range(len(self.classes), nc)]
        cid = cls_scores.argmax(1)
        sc = cls_scores[np.arange(len(cid)), cid]
        keep = sc >= min([self.conf] + list(self.class_thr.values()))
        boxes, cid, sc = boxes[keep], cid[keep], sc[keep]
        if len(sc) == 0:
            return []
        xyxy = np.stack([(boxes[:, 0] - boxes[:, 2] / 2 - dx) / r, (boxes[:, 1] - boxes[:, 3] / 2 - dy) / r,
                         (boxes[:, 0] + boxes[:, 2] / 2 - dx) / r, (boxes[:, 1] + boxes[:, 3] / 2 - dy) / r], 1)
        res = []
        for c in np.unique(cid):
            m = cid == c
            b = xyxy[m]
            s = sc[m]
            idx = cv2.dnn.NMSBoxes([[float(v[0]), float(v[1]), float(v[2] - v[0]), float(v[3] - v[1])] for v in b],
                                   s.tolist(), 0.01, 0.5)
            name = self.classes[int(c)] if int(c) < len(self.classes) else f"class{c}"
            thr = self.class_thr.get(name, self.conf)
            for i in np.array(idx).reshape(-1):
                if s[i] >= thr:
                    v = b[i]
                    res.append(Detection(float(max(0, v[0])), float(max(0, v[1])), float(min(fw - 1, v[2])),
                                         float(min(fh - 1, v[3])), float(s[i]), name))
        return res


def decode_centernet(out: np.ndarray, classes: list[str], stride: int, sx: float, sy: float,
                     conf: float, class_thr: dict | None = None, max_det: int = 100) -> list[Detection]:
    nc = len(classes)
    heat = out[:nc]
    size = out[nc:nc + 2]
    kernel = np.ones((3, 3), np.uint8)
    res = []
    class_thr = class_thr or {}
    for c in range(nc):
        hm = heat[c]
        thr = class_thr.get(classes[c], conf)
        if hm.max() < thr:
            continue
        mx = cv2.dilate(hm, kernel)
        ys, xs = np.where((hm >= mx) & (hm >= thr))
        for y, x in zip(ys, xs):
            bw = math_exp(size[0, y, x]) * stride * sx
            bh = math_exp(size[1, y, x]) * stride * sy
            # sub-cell refinement: weighted centroid of the 3x3 neighbourhood
            y0, y1 = max(0, y - 1), min(hm.shape[0], y + 2)
            x0, x1 = max(0, x - 1), min(hm.shape[1], x + 2)
            patch = hm[y0:y1, x0:x1]
            gy, gx = np.mgrid[y0:y1, x0:x1]
            wsum = patch.sum() + 1e-6
            cy = ((gy * patch).sum() / wsum + 0.5) * stride * sy
            cx = ((gx * patch).sum() / wsum + 0.5) * stride * sx
            res.append(Detection(float(cx - bw / 2), float(cy - bh / 2), float(cx + bw / 2), float(cy + bh / 2),
                                 float(hm[y, x]), classes[c]))
    res.sort(key=lambda d: -d.score)
    return res[:max_det]


def math_exp(v: float) -> float:
    return float(np.exp(np.clip(v, -4, 6)))


class ModelRegistry:
    """Holds the active detector; supports atomic hot-swap while pipelines run."""

    def __init__(self):
        self._det: OnnxDetector | None = None
        self._lock = threading.Lock()
        self.version = 0

    def load(self, path: str | Path, **kw) -> OnnxDetector:
        det = OnnxDetector(path, **kw)
        # warm-up so the first live frame is not slow
        det.detect(np.zeros((360, 640, 3), np.uint8))
        with self._lock:
            self._det = det
            self.version += 1
        log.info("Detector loaded: %s (%s) providers=%s", det.name, det.format, det.providers)
        return det

    @property
    def detector(self) -> OnnxDetector | None:
        with self._lock:
            return self._det


def default_model_path() -> Path:
    from nomload.config import bundled_models_dir
    return bundled_models_dir() / "starter_detector.onnx"

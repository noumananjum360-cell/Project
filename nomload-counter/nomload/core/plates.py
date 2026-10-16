"""Number plate localisation and OCR for Pakistani plates.

Pipeline:
  1. Find plate candidates: detector boxes of class ``plate`` (if the model has
     it) inside the calibrated plate region, otherwise a classical localiser
     (bright rectangle with dark character strokes, aspect 1.8 - 6).
  2. Segment characters (Otsu + connected components), dropping the small
     province header ("PUNJAB", "SINDH"...), year stickers and the hyphen.
  3. Classify each character with the bundled ONNX classifier
     (``models/plate_ocr.onnx``, 36 classes A-Z 0-9), or run a PaddleOCR
     recognition model (CTC) if one is configured.
  4. Normalise with the Pakistani format rules (plate_formats.parse) and vote
     across frames, so one blurred frame cannot win.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from nomload.core import plate_formats

log = logging.getLogger(__name__)

CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
GLYPH_W, GLYPH_H = 16, 24


def _small_session(ort):
    """Plate models are tiny: one thread, no busy-spinning (keeps the UI responsive)."""
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    so.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return so


@dataclass
class PlateRead:
    text: str
    raw: str
    confidence: float
    province: str
    box: tuple
    crop: np.ndarray | None = None
    ts: float = field(default_factory=time.time)


# --------------------------------------------------------------------------- localisation
def find_plate_candidates(frame: np.ndarray, roi=None, max_candidates: int = 4) -> list[tuple]:
    """Classical plate localiser. Returns boxes (x0,y0,x1,y1) in frame coords."""
    x_off, y_off = 0, 0
    img = frame
    if roi:
        x0, y0, x1, y1 = roi
        img = frame[max(0, y0):y1, max(0, x0):x1]
        x_off, y_off = max(0, x0), max(0, y0)
    if img.size == 0:
        return []
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, w // 25), max(3, h // 40)))
    blackhat = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, k)
    gx = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=3)
    gx = cv2.convertScaleAbs(gx)
    gx = cv2.GaussianBlur(gx, (5, 5), 0)
    gx = cv2.morphologyEx(gx, cv2.MORPH_CLOSE, k)
    _, th = cv2.threshold(gx, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    th = cv2.erode(th, None, iterations=1)
    th = cv2.dilate(th, None, iterations=2)
    # bright background check
    bright = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bh < 10 or bw < 30:
            continue
        ar = bw / float(bh)
        if not (1.6 <= ar <= 7.0):
            continue
        if bw * bh < 0.002 * w * h:
            continue
        fill = bright[y:y + bh, x:x + bw].mean() / 255
        score = fill * min(1.0, bw * bh / (0.02 * w * h))
        pad_x, pad_y = int(bw * 0.08), int(bh * 0.25)
        out.append((score, (x + x_off - pad_x, y + y_off - pad_y, x + x_off + bw + pad_x, y + y_off + bh + pad_y)))
    out.sort(key=lambda t: -t[0])
    H, W = frame.shape[:2]
    return [(max(0, a), max(0, b), min(W - 1, c), min(H - 1, d)) for _, (a, b, c, d) in out[:max_candidates]]


# --------------------------------------------------------------------------- segmentation
def segment_characters(plate_bgr: np.ndarray) -> list[np.ndarray]:
    """Return normalised glyph images (GLYPH_H x GLYPH_W float32, ink=1), left to right."""
    if plate_bgr is None or plate_bgr.size == 0:
        return []
    g = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY) if plate_bgr.ndim == 3 else plate_bgr
    scale = 80.0 / max(1, g.shape[0])
    g = cv2.resize(g, (max(8, int(g.shape[1] * scale)), 80), interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # polarity: judge on the plate centre (the crop may include dark truck body)
    H0, W0 = bw.shape
    centre = bw[int(H0 * 0.25):int(H0 * 0.75), int(W0 * 0.2):int(W0 * 0.8)]
    if centre.size and centre.mean() > 140:
        bw = 255 - bw
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    H, W = bw.shape
    comps = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if h < 0.25 * H or h > 0.95 * H or w > 0.3 * W or a < 20:
            continue
        if x <= 1 or x + w >= W - 1:  # touching the border -> plate frame
            continue
        comps.append((x, y, w, h, i))
    if not comps:
        return []
    hmax = max(c[3] for c in comps)
    comps = [c for c in comps if c[3] >= 0.68 * hmax]
    # keep the dominant text row (median centre line)
    cy = np.median([c[1] + c[3] / 2 for c in comps])
    comps = [c for c in comps if abs((c[1] + c[3] / 2) - cy) < 0.35 * hmax]
    comps.sort(key=lambda c: c[0])
    glyphs = []
    for x, y, w, h, i in comps:
        m = (lab[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        glyphs.append(normalise_glyph(m))
    return glyphs


def normalise_glyph(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    side_h = int(h * 1.0)
    side_w = max(w, int(h * GLYPH_W / GLYPH_H))
    canvas = np.zeros((side_h, side_w), np.uint8)
    x0 = (side_w - w) // 2
    canvas[:, x0:x0 + w] = mask[:side_h]
    g = cv2.resize(canvas, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)
    return g.astype(np.float32) / 255.0


# --------------------------------------------------------------------------- recognisers
class CharOCR:
    """Per-character ONNX classifier (bundled)."""

    def __init__(self, path: str | Path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(path), _small_session(ort), providers=["CPUExecutionProvider"])
        meta = self.sess.get_modelmeta().custom_metadata_map
        self.charset = meta.get("charset", CHARSET)
        self.inp = self.sess.get_inputs()[0].name

    def read(self, plate_bgr: np.ndarray) -> tuple[str, float]:
        glyphs = segment_characters(plate_bgr)
        if not glyphs:
            return "", 0.0
        x = np.stack([g.reshape(-1) for g in glyphs]).astype(np.float32)
        prob = self.sess.run(None, {self.inp: x})[0]
        idx = prob.argmax(1)
        conf = float(np.prod(prob[np.arange(len(idx)), idx]) ** (1 / len(idx)))
        return "".join(self.charset[i] for i in idx), conf


class PaddleRecOCR:
    """PaddleOCR text-recognition model exported to ONNX (CTC head).

    Configure with the .onnx file and the dictionary .txt used in training
    (one character per line; index 0 is the CTC blank).
    """

    def __init__(self, path: str | Path, dict_path: str | Path, height: int = 48):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(path), _small_session(ort), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        chars = Path(dict_path).read_text(encoding="utf-8").splitlines()
        self.chars = ["<blank>"] + chars + [" "]
        self.h = height

    def read(self, plate_bgr: np.ndarray) -> tuple[str, float]:
        h, w = plate_bgr.shape[:2]
        nw = max(16, int(w * self.h / h))
        img = cv2.resize(plate_bgr, (nw, self.h)).astype(np.float32) / 255.0
        img = (img - 0.5) / 0.5
        x = img.transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.inp: x})[0][0]  # [T, C]
        idx = out.argmax(1)
        probs = out.max(1)
        text, confs, prev = [], [], -1
        for i, p in zip(idx, probs):
            if i != prev and i != 0 and i < len(self.chars):
                text.append(self.chars[i])
                confs.append(p)
            prev = i
        return "".join(text).upper(), float(np.mean(confs)) if confs else 0.0


def load_ocr(settings: dict | None = None):
    from nomload.config import bundled_models_dir, user_models_dir
    settings = settings or {}
    if settings.get("paddle_rec_model") and settings.get("paddle_rec_dict"):
        try:
            return PaddleRecOCR(settings["paddle_rec_model"], settings["paddle_rec_dict"])
        except Exception as e:
            log.warning("PaddleOCR model failed to load (%s); using built-in OCR", e)
    for d in (user_models_dir(), bundled_models_dir()):
        p = d / "plate_ocr.onnx"
        if p.exists():
            return CharOCR(p)
    return None


# --------------------------------------------------------------------------- reader
class PlateReader:
    def __init__(self, ocr=None, min_votes: int = 5, min_agreement: float = 0.6):
        self.ocr = ocr
        self.min_votes = min_votes
        self.min_agreement = min_agreement
        self.votes: dict[str, list[PlateRead]] = {}

    def reset(self):
        self.votes.clear()

    def read_frame(self, frame: np.ndarray, roi=None, plate_dets=None) -> PlateRead | None:
        """Read the best plate in a frame (no voting)."""
        if self.ocr is None:
            return None
        boxes = []
        for d in plate_dets or []:
            b = d.box if hasattr(d, "box") else d
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            if roi is None or (roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]):
                bw, bh = b[2] - b[0], b[3] - b[1]
                # generous margin: characters touching the crop edge are discarded by segmentation
                boxes.append((int(b[0] - bw * 0.12), int(b[1] - bh * 0.18), int(b[2] + bw * 0.12), int(b[3] + bh * 0.18)))
        if not boxes:
            boxes = find_plate_candidates(frame, roi)
        H, W = frame.shape[:2]
        # the whole plate region (or a frame that is itself a plate crop) as a last resort
        boxes.append(tuple(roi) if roi else (0, 0, W, H))
        best = None
        for b in boxes:
            x0, y0, x1, y1 = max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3])
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0 or crop.shape[0] < 8:
                continue
            raw, conf = self.ocr.read(crop)
            p = plate_formats.parse(raw)
            if not p.text:
                continue
            score = conf * p.plausibility
            if best is None or score > best.confidence:
                best = PlateRead(p.text, raw, round(score, 3), p.province, (x0, y0, x1, y1), crop.copy())
        return best

    def add(self, read: PlateRead | None):
        if read and read.text:
            self.votes.setdefault(read.text, []).append(read)

    def best(self) -> PlateRead | None:
        if not self.votes:
            return None
        total = sum(len(v) for v in self.votes.values())
        text, reads = max(self.votes.items(), key=lambda kv: sum(r.confidence for r in kv[1]))
        top = max(reads, key=lambda r: r.confidence)
        agree = len(reads) / total
        conf = round(min(1.0, (sum(r.confidence for r in reads) / len(reads)) * (0.5 + 0.5 * agree)), 3)
        return PlateRead(text, top.raw, conf, top.province, top.box, top.crop, top.ts)

    def confident(self) -> bool:
        """Accept only when one reading clearly dominates (avoids locking onto a cut-off read)."""
        b = self.best()
        if not b:
            return False
        n = len(self.votes.get(b.text, []))
        total = sum(len(v) for v in self.votes.values())
        return n >= self.min_votes and n / total >= self.min_agreement and b.confidence >= 0.6


def export_char_ocr_onnx(W1, b1, W2, b2, path: str):
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    nodes = [
        helper.make_node("Gemm", ["x", "W1", "b1"], ["h"], transB=1),
        helper.make_node("Relu", ["h"], ["hr"]),
        helper.make_node("Gemm", ["hr", "W2", "b2"], ["logits"], transB=1),
        helper.make_node("Softmax", ["logits"], ["prob"], axis=1),
    ]
    inits = [numpy_helper.from_array(W1.astype(np.float32), "W1"), numpy_helper.from_array(b1.astype(np.float32), "b1"),
             numpy_helper.from_array(W2.astype(np.float32), "W2"), numpy_helper.from_array(b2.astype(np.float32), "b2")]
    g = helper.make_graph(nodes, "plate_char_ocr",
                          [helper.make_tensor_value_info("x", TensorProto.FLOAT, ["N", GLYPH_W * GLYPH_H])],
                          [helper.make_tensor_value_info("prob", TensorProto.FLOAT, ["N", len(CHARSET)])], inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)], producer_name="nomload")
    m.ir_version = 8
    for k, v in {"format": "nomload-char-ocr", "charset": CHARSET,
                 "glyph": json.dumps([GLYPH_H, GLYPH_W])}.items():
        e = m.metadata_props.add()
        e.key, e.value = k, v
    onnx.checker.check_model(m)
    onnx.save(m, path)

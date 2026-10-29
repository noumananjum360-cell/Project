"""Train the plate character classifier (NumPy MLP -> ONNX).

Training glyphs are produced by rendering plates with real fonts, degrading
them (perspective, blur, low resolution, noise) and running them through the
*same* segmentation used at runtime, so train and inference match exactly.
Plate crops corrected by clerks (stored under datasets/plates) can be added
to adapt the OCR to the site's real plates.
"""
from __future__ import annotations

import random
from pathlib import Path

import cv2
import numpy as np

from nomload.core import plate_formats
from nomload.core.plates import CHARSET, export_char_ocr_onnx, segment_characters


def degrade(img: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    d = 0.06
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[rng.uniform(-d, d) * w, rng.uniform(-d, d) * h], [w + rng.uniform(-d, d) * w, rng.uniform(-d, d) * h],
                      [w + rng.uniform(-d, d) * w, h + rng.uniform(-d, d) * h], [rng.uniform(-d, d) * w, h + rng.uniform(-d, d) * h]])
    M = cv2.getPerspectiveTransform(src, dst)
    img = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    th = rng.randint(22, 70)
    small = cv2.resize(img, (int(w * th / h), th), interpolation=cv2.INTER_AREA)
    if rng.random() < 0.5:
        small = cv2.GaussianBlur(small, (3, 3), rng.uniform(0.3, 1.0))
    small = (small.astype(np.float32) * rng.uniform(0.6, 1.2) + rng.uniform(-30, 30)
             + np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(0, 8), small.shape))
    small = small.clip(0, 255).astype(np.uint8)
    if rng.random() < 0.4:
        ok, enc = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(30, 80)])
        small = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return small


def synth_glyphs(n_plates: int, seed: int = 0):
    from nomload.training.qt_render import available_fonts, render_plate
    rng = random.Random(seed)
    fonts = available_fonts()
    X, Y = [], []
    for _ in range(n_plates):
        if rng.random() < 0.5:
            text, prov = plate_formats.random_plate(rng)
        else:  # uniform character coverage
            letters = "".join(rng.choice(CHARSET[:26]) for _ in range(rng.randint(2, 3)))
            text, prov = f"{letters}-{rng.randint(1, 9999)}", rng.choice(list(plate_formats.PROVINCE_HEADERS))
        style = rng.choice(["white", "white", "yellow", "green"])
        img = render_plate(text, prov, style, rng.choice(fonts), bold=rng.random() < 0.8)
        img = degrade(img, rng)
        glyphs = segment_characters(img)
        chars = plate_formats.clean(text)
        if len(glyphs) != len(chars):
            continue
        for g, c in zip(glyphs, chars):
            X.append(g.reshape(-1))
            Y.append(CHARSET.index(c))
    return np.array(X, np.float32), np.array(Y, np.int64)


def corrected_glyphs(folder: Path):
    """Glyphs from clerk-corrected plate crops: files named <TEXT>__<id>.jpg."""
    X, Y = [], []
    if not folder.exists():
        return np.zeros((0, 384), np.float32), np.zeros(0, np.int64)
    for p in folder.glob("*.jpg"):
        text = plate_formats.clean(p.stem.split("__")[0])
        img = cv2.imread(str(p))
        if img is None:
            continue
        g = segment_characters(img)
        if len(g) == len(text):
            for gl, c in zip(g, text):
                X.append(gl.reshape(-1)); Y.append(CHARSET.index(c))
    return np.array(X, np.float32).reshape(-1, 384), np.array(Y, np.int64)


def train_mlp(X, Y, hidden=256, epochs=30, lr=2e-3, seed=0, log=print):
    rng = np.random.default_rng(seed)
    d, k = X.shape[1], len(CHARSET)
    W1 = (rng.standard_normal((hidden, d)) * np.sqrt(2 / d)).astype(np.float32)
    b1 = np.zeros(hidden, np.float32)
    W2 = (rng.standard_normal((k, hidden)) * np.sqrt(1 / hidden)).astype(np.float32)
    b2 = np.zeros(k, np.float32)
    params = [W1, b1, W2, b2]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    t = 0
    n = len(X)
    idx_all = np.arange(n)
    for ep in range(epochs):
        rng.shuffle(idx_all)
        correct = 0
        for s in range(0, n, 128):
            idx = idx_all[s:s + 128]
            x = X[idx]
            # light augmentation: random pixel shift
            if rng.random() < 0.5:
                x = np.roll(x.reshape(-1, 24, 16), rng.integers(-1, 2), axis=2).reshape(len(idx), -1)
            y = Y[idx]
            h = x @ W1.T + b1
            hr = np.maximum(h, 0)
            lo = hr @ W2.T + b2
            lo -= lo.max(1, keepdims=True)
            p = np.exp(lo)
            p /= p.sum(1, keepdims=True)
            correct += int((p.argmax(1) == y).sum())
            g = p.copy()
            g[np.arange(len(y)), y] -= 1
            g /= len(y)
            dW2 = g.T @ hr
            db2 = g.sum(0)
            dh = (g @ W2) * (h > 0)
            dW1 = dh.T @ x
            db1 = dh.sum(0)
            t += 1
            cur = lr * (0.5 * (1 + np.cos(np.pi * ep / epochs)))
            for i, gr in enumerate([dW1, db1, dW2, db2]):
                m[i] = 0.9 * m[i] + 0.1 * gr
                v[i] = 0.999 * v[i] + 0.001 * gr * gr
                params[i] -= cur * (m[i] / (1 - 0.9 ** t)) / (np.sqrt(v[i] / (1 - 0.999 ** t)) + 1e-8)
        log(f"epoch {ep + 1}/{epochs} train acc {correct / n:.4f}")
    return W1, b1, W2, b2


def evaluate(params, X, Y) -> float:
    W1, b1, W2, b2 = params
    lo = np.maximum(X @ W1.T + b1, 0) @ W2.T + b2
    return float((lo.argmax(1) == Y).mean())


def train_and_export(out_path: str, n_plates: int = 6000, extra_folder: Path | None = None, log=print) -> float:
    X, Y = synth_glyphs(n_plates, seed=1)
    if extra_folder:
        Xe, Ye = corrected_glyphs(extra_folder)
        if len(Xe):
            X = np.concatenate([X] + [Xe] * 5)
            Y = np.concatenate([Y] + [Ye] * 5)
    log(f"{len(X)} glyphs")
    params = train_mlp(X, Y, log=log)
    Xv, Yv = synth_glyphs(800, seed=999)
    acc = evaluate(params, Xv, Yv)
    log(f"validation char accuracy {acc:.4f}")
    export_char_ocr_onnx(*params, out_path)
    return acc

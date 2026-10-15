"""Fine-tuning jobs: built-in NumPy detector (always available) or Ultralytics YOLO (optional)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import time
from pathlib import Path

import numpy as np

from nomload.config import user_models_dir
from nomload.core.detector import OnnxDetector
from nomload.core.geometry import iou
from nomload.training.dataset import Dataset
from nomload.training.nn import CenterNetLite, TrainConfig, train


def ultralytics_available() -> bool:
    return importlib.util.find_spec("ultralytics") is not None


def build_from_base(classes: list[str], base_model: str | None) -> CenterNetLite:
    """New network for ``classes``; backbone (and matching head rows) copied from a base model."""
    net = CenterNetLite(classes, (192, 320), seed=1)
    if base_model and Path(base_model).exists():
        try:
            base = CenterNetLite.from_onnx(base_model)
        except Exception:
            return net
        for a, b in zip(net.layers, base.layers):
            a.W[...] = b.W
            a.b[...] = b.b
        for i, c in enumerate(classes):
            if c in base.classes:
                j = base.classes.index(c)
                net.head.W[i] = base.head.W[j]
                net.head.b[i] = base.head.b[j]
        nb = len(base.classes)
        net.head.W[len(classes):] = base.head.W[nb:nb + 2]
        net.head.b[len(classes):] = base.head.b[nb:nb + 2]
    return net


def evaluate_detector(det: OnnxDetector, samples: list, classes: list[str], iou_thr: float = 0.5) -> dict:
    """Precision / recall per class at IoU 0.5 on labelled samples."""
    stats = {c: {"tp": 0, "fp": 0, "fn": 0} for c in classes}
    for img, labels in samples:
        dets = det.detect(img)
        gts = [(classes[c], (x0, y0, x1, y1)) for c, x0, y0, x1, y1 in labels if c < len(classes)]
        used = set()
        for d in sorted(dets, key=lambda d: -d.score):
            if d.cls not in stats:
                continue
            best, bi = 0.0, -1
            for i, (gc, gb) in enumerate(gts):
                if i in used or gc != d.cls:
                    continue
                v = iou(d.box, gb)
                if v > best:
                    best, bi = v, i
            if best >= iou_thr:
                used.add(bi)
                stats[d.cls]["tp"] += 1
            else:
                stats[d.cls]["fp"] += 1
        for i, (gc, _gb) in enumerate(gts):
            if i not in used and gc in stats:
                stats[gc]["fn"] += 1
    out = {}
    for c, s in stats.items():
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        out[c] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
                  "objects": tp + fn}
    return out


class TrainJob:
    """Runs in a worker thread. Callbacks: log(str), progress(done, total, loss)."""

    def __init__(self, ds: Dataset, backend: str = "builtin", iterations: int = 1500, base_model: str | None = None,
                 log=print, progress=None):
        self.ds = ds
        self.backend = backend
        self.iterations = iterations
        self.base_model = base_model
        self.log = log
        self.progress = progress
        self._stop = False
        self.result: dict = {}

    def stop(self):
        self._stop = True

    def run(self) -> dict:
        st = self.ds.stats()
        if st["labeled"] < 5:
            raise ValueError("Annotate at least 5 images (50+ recommended) before training.")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = user_models_dir() / f"detector_{self.ds.name}_{stamp}.onnx"
        if self.backend == "ultralytics":
            self._run_ultralytics(out)
        else:
            self._run_builtin(out)
        if self._stop and not out.exists():
            raise RuntimeError("Training stopped.")
        det = OnnxDetector(out, conf_threshold=0.35)
        val = self.ds.samples("val") or self.ds.samples("all")[:30]
        metrics = evaluate_detector(det, val, self.ds.classes)
        self.log("Validation: " + json.dumps(metrics))
        info = {"path": str(out), "dataset": self.ds.name, "backend": self.backend, "created": stamp,
                "images": st["labeled"], "metrics": metrics, "classes": self.ds.classes}
        out.with_suffix(".json").write_text(json.dumps(info, indent=2))
        self.result = info
        return info

    def _run_builtin(self, out: Path):
        samples = self.ds.samples("train")
        self.log(f"Built-in trainer: {len(samples)} training images, classes {self.ds.classes}")
        net = build_from_base(self.ds.classes, self.base_model)

        def prog(i, n, loss, el):
            self.log(f"iteration {i}/{n}  loss {loss:.4f}  ({el:.0f}s)")
            if self.progress:
                self.progress(i, n, loss)

        train(net, samples, TrainConfig(iterations=self.iterations, batch=8, lr=1e-3 if self.base_model else 2e-3,
                                        log_every=25), prog, lambda: self._stop)
        net.to_onnx(str(out), {"name": f"{self.ds.name} ({time.strftime('%d-%b %H:%M')})", "trained_on": self.ds.name})
        self.log(f"Saved {out}")

    def _run_ultralytics(self, out: Path):
        from ultralytics import YOLO  # optional dependency
        work = self.ds.root / "yolo_run"
        if work.exists():
            shutil.rmtree(work)
        imgs = [p for p in self.ds.image_files() if self.ds.is_labeled(p)]
        rng = np.random.default_rng(0)
        rng.shuffle(imgs)
        nv = max(1, len(imgs) // 7)
        for split, items in (("val", imgs[:nv]), ("train", imgs[nv:])):
            (work / "images" / split).mkdir(parents=True, exist_ok=True)
            (work / "labels" / split).mkdir(parents=True, exist_ok=True)
            for p in items:
                shutil.copy2(p, work / "images" / split / p.name)
                shutil.copy2(self.ds.label_path(p), work / "labels" / split / (p.stem + ".txt"))
        yaml = work / "data.yaml"
        yaml.write_text(f"path: {work.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n" +
                        "".join(f"  {i}: {c}\n" for i, c in enumerate(self.ds.classes)))
        base = self.base_model if self.base_model and self.base_model.endswith(".pt") else "yolov8n.yaml"
        self.log(f"Ultralytics YOLO training from {base} ({len(imgs)} images)")
        model = YOLO(base)
        epochs = max(5, self.iterations // 50)

        def on_epoch(trainer):
            if self.progress:
                self.progress(trainer.epoch + 1, epochs, float(trainer.loss.sum()) if trainer.loss is not None else 0.0)
            if self._stop:
                trainer.stop = True

        model.add_callback("on_train_epoch_end", on_epoch)
        model.train(data=str(yaml), epochs=epochs, imgsz=640, batch=8, project=str(work), name="run", device="cpu",
                    workers=0, verbose=False)
        onnx_path = Path(model.export(format="onnx", imgsz=640, opset=12, simplify=False))
        shutil.copy2(onnx_path, out)
        self.log(f"Saved {out}")


def list_models() -> list[dict]:
    from nomload.config import bundled_models_dir
    out = []
    starter = bundled_models_dir() / "starter_detector.onnx"
    if starter.exists():
        out.append({"path": str(starter), "name": "Starter model (synthetic, bundled)", "created": "", "metrics": {}})
    for p in sorted(user_models_dir().glob("detector_*.onnx"), reverse=True):
        meta = p.with_suffix(".json")
        info = json.loads(meta.read_text()) if meta.exists() else {}
        out.append({"path": str(p), "name": p.stem, "created": info.get("created", ""), "metrics": info.get("metrics", {}),
                    "images": info.get("images"), "backend": info.get("backend", "")})
    return out

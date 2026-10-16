"""Annotation datasets in YOLO format + frame extraction from customer video.

Layout:  datasets/<name>/images/*.jpg   labels/*.txt (class cx cy w h, normalised)
         datasets/<name>/classes.txt    (one class per line)
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import cv2
import numpy as np

from nomload.config import DEFAULT_CLASSES, datasets_dir


class Dataset:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.images = self.root / "images"
        self.labels = self.root / "labels"
        self.images.mkdir(parents=True, exist_ok=True)
        self.labels.mkdir(parents=True, exist_ok=True)
        cf = self.root / "classes.txt"
        if not cf.exists():
            cf.write_text("\n".join(DEFAULT_CLASSES), encoding="utf-8")

    @property
    def name(self) -> str:
        return self.root.name

    @classmethod
    def create(cls, name: str, classes: list[str] | None = None) -> "Dataset":
        safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip() or "dataset"
        ds = cls(datasets_dir() / safe)
        if classes:
            ds.classes = classes
        return ds

    @staticmethod
    def list_all() -> list["Dataset"]:
        return [Dataset(p) for p in sorted(datasets_dir().iterdir()) if p.is_dir() and (p / "images").exists()]

    @property
    def classes(self) -> list[str]:
        return [c.strip() for c in (self.root / "classes.txt").read_text(encoding="utf-8").splitlines() if c.strip()]

    @classes.setter
    def classes(self, v: list[str]):
        (self.root / "classes.txt").write_text("\n".join(v), encoding="utf-8")

    def add_class(self, name: str) -> int:
        cl = self.classes
        if name not in cl:
            cl.append(name)
            self.classes = cl
        return cl.index(name)

    def image_files(self) -> list[Path]:
        return sorted([p for p in self.images.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])

    def label_path(self, img: Path) -> Path:
        return self.labels / (img.stem + ".txt")

    def is_labeled(self, img: Path) -> bool:
        return self.label_path(img).exists()

    def read_labels(self, img: Path, w: int, h: int) -> list[tuple[int, float, float, float, float]]:
        lp = self.label_path(img)
        out = []
        if lp.exists():
            for line in lp.read_text().splitlines():
                parts = line.split()
                if len(parts) == 5:
                    c, cx, cy, bw, bh = int(parts[0]), *map(float, parts[1:])
                    out.append((c, (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
        return out

    def write_labels(self, img: Path, boxes: list, w: int, h: int):
        lines = []
        for c, x0, y0, x1, y1 in boxes:
            x0, x1 = sorted((max(0, x0), min(w - 1, x1)))
            y0, y1 = sorted((max(0, y0), min(h - 1, y1)))
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            lines.append(f"{int(c)} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")
        self.label_path(img).write_text("\n".join(lines))

    # ------------------------------------------------------------ removing data
    @staticmethod
    def source_of(img: Path) -> str:
        """Video an extracted frame came from (frames are saved as <video>_<frame>.jpg)."""
        stem = img.stem
        head, _sep, tail = stem.rpartition("_")
        return head if head and tail.isdigit() else stem

    def sources(self) -> dict[str, int]:
        """{video name: number of frames} for every video in the dataset."""
        out: dict[str, int] = {}
        for p in self.image_files():
            k = self.source_of(p)
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    def delete_images(self, imgs: list[Path]) -> int:
        """Delete images and their labels from the dataset (they are no longer used for training)."""
        n = 0
        for img in imgs:
            img = Path(img)
            if img.parent != self.images:
                continue  # only files inside this dataset
            self.label_path(img).unlink(missing_ok=True)
            if img.exists():
                img.unlink()
                n += 1
        return n

    def delete_source(self, source: str) -> int:
        """Delete every frame taken from one video."""
        return self.delete_images([p for p in self.image_files() if self.source_of(p) == source])

    def clear_labels(self, img: Path):
        self.label_path(img).unlink(missing_ok=True)

    def delete(self):
        """Delete the whole dataset folder."""
        import shutil
        if self.root.parent == datasets_dir():
            shutil.rmtree(self.root, ignore_errors=True)

    def stats(self) -> dict:
        imgs = self.image_files()
        labeled = [i for i in imgs if self.is_labeled(i)]
        counts = [0] * len(self.classes)
        for i in labeled:
            for line in self.label_path(i).read_text().splitlines():
                p = line.split()
                if p and int(p[0]) < len(counts):
                    counts[int(p[0])] += 1
        return {"images": len(imgs), "labeled": len(labeled), "per_class": dict(zip(self.classes, counts))}

    def samples(self, split: str = "all", val_fraction: float = 0.15, seed: int = 0):
        """Load labelled samples as (bgr, [(cls, x0,y0,x1,y1)]) - deterministic train/val split."""
        imgs = [i for i in self.image_files() if self.is_labeled(i)]
        rng = random.Random(seed)
        rng.shuffle(imgs)
        nv = max(1, int(len(imgs) * val_fraction)) if len(imgs) >= 8 else 0
        sel = imgs if split == "all" else (imgs[nv:] if split == "train" else imgs[:nv])
        out = []
        for p in sel:
            im = cv2.imread(str(p))
            if im is None:
                continue
            h, w = im.shape[:2]
            out.append((im, [(c, x0, y0, x1, y1) for c, x0, y0, x1, y1 in self.read_labels(p, w, h)]))
        return out

    def meta(self) -> dict:
        f = self.root / "meta.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def set_meta(self, **kw):
        m = self.meta()
        m.update(kw)
        (self.root / "meta.json").write_text(json.dumps(m, indent=2))


def extract_frames(video: str | Path, ds: Dataset, every_n: int = 15, max_frames: int = 300,
                   skip_similar: bool = True, progress=None, should_stop=None) -> int:
    """Save every Nth frame (skipping near-duplicates) into the dataset."""
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    i = saved = 0
    last_small = None
    stem = Path(str(video)).stem[:30].replace(" ", "_")
    while saved < max_frames:
        ok, fr = cap.read()
        if not ok:
            break
        if i % every_n == 0:
            small = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (64, 36)).astype(np.float32)
            if not skip_similar or last_small is None or np.abs(small - last_small).mean() > 2.0:
                cv2.imwrite(str(ds.images / f"{stem}_{i:06d}.jpg"), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
                saved += 1
                last_small = small
        i += 1
        if progress and i % 30 == 0:
            progress(i, total, saved)
        if should_stop and should_stop():
            break
    cap.release()
    return saved


def add_synthetic(ds: Dataset, n: int = 200, seed: int | None = None) -> int:
    """Add rendered synthetic loading scenes with exact labels (demo / bootstrap data)."""
    from nomload.training.synth import training_samples
    classes = ds.classes
    seed = seed if seed is not None else int(time.time())
    k = 0
    for img, labels in training_samples(n, seed=seed, classes=DEFAULT_CLASSES):
        p = ds.images / f"synthetic_{seed}_{k:05d}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        h, w = img.shape[:2]
        boxes = []
        for c, x0, y0, x1, y1 in labels:
            name = DEFAULT_CLASSES[c]
            if name in classes:
                boxes.append((classes.index(name), x0, y0, x1, y1))
        ds.write_labels(p, boxes, w, h)
        k += 1
    return k

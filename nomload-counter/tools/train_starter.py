"""Train the bundled starter detector on synthetic loading scenes.

    python tools/train_starter.py --samples 3000 --iterations 4000

Writes models/starter_detector.onnx. Takes ~30-60 min on a 4-core CPU.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nomload.config import DEFAULT_CLASSES  # noqa: E402
from nomload.training.nn import CenterNetLite, TrainConfig, train  # noqa: E402
from nomload.training.synth import training_samples  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=3000)
    ap.add_argument("--iterations", type=int, default=4000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--out", default=str(ROOT / "models" / "starter_detector.onnx"))
    ap.add_argument("--resume", default="")
    args = ap.parse_args()

    t0 = time.time()
    samples = list(training_samples(args.samples, seed=12345))
    print(f"generated {len(samples)} samples in {time.time() - t0:.0f}s", flush=True)
    net = CenterNetLite(DEFAULT_CLASSES, (192, 320), seed=0)
    if args.resume:
        net = CenterNetLite.from_onnx(args.resume)

    ckpt = Path(args.out).with_suffix(".ckpt.onnx")

    def progress(i, n, loss, el):
        print(f"iter {i}/{n} loss {loss:.4f} elapsed {el:.0f}s", flush=True)
        if i % 500 == 0:
            net.to_onnx(str(ckpt), {"name": "NomLoad starter (checkpoint)"})

    train(net, samples, TrainConfig(iterations=args.iterations, batch=args.batch, lr=args.lr), progress)
    net.to_onnx(args.out, {"name": "NomLoad starter detector", "trained_on": "synthetic",
                           "version": "1.0"})
    if ckpt.exists():
        ckpt.unlink()
    print("saved", args.out, f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

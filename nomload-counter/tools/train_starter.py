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

if os.name != "nt":  # Windows renders off-screen natively with its system fonts

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
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--hard", action="store_true", help="emphasise crowded / conveyor scenes")
    ap.add_argument("--recipes", default="", help="comma separated scene recipes, e.g. conveyor,cartons")
    args = ap.parse_args()

    t0 = time.time()
    if args.recipes:
        samples = list(training_samples(args.samples, seed=args.seed, recipes=args.recipes.split(","),
                                        density=(1.0, 1.8)))
    elif args.hard:
        samples = list(training_samples(args.samples, seed=args.seed,
                                        recipes=["conveyor", "conveyor", "mixed", "mixed", "cartons", "bags"],
                                        density=(1.0, 2.0)))
    else:
        samples = list(training_samples(args.samples, seed=args.seed))
    print(f"generated {len(samples)} samples in {time.time() - t0:.0f}s", flush=True)
    net = CenterNetLite(DEFAULT_CLASSES, (192, 320), seed=0)
    if args.resume:
        net = CenterNetLite.from_onnx(args.resume)

    ckpt = Path(args.out).with_suffix(".ckpt.onnx")

    def progress(i, n, loss, el):
        print(f"iter {i}/{n} loss {loss:.4f} elapsed {el:.0f}s", flush=True)
        if i % 500 == 1 and i > 1:
            net.to_onnx(str(ckpt), {"name": "NomLoad starter (checkpoint)"})

    train(net, samples, TrainConfig(iterations=args.iterations, batch=args.batch, lr=args.lr), progress)
    net.to_onnx(args.out, {"name": "NomLoad starter detector", "trained_on": "synthetic",
                           "version": "1.0"})
    if ckpt.exists():
        ckpt.unlink()
    print("saved", args.out, f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

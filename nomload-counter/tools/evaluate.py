"""Measure counting accuracy on the sample videos (or your own with an answer key).

    python tools/evaluate.py [--model models/starter_detector.onnx] [--folder samples] [--skip 0]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nomload.core.detector import ModelRegistry  # noqa: E402
from nomload.services.evaluation import evaluate_folder  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models" / "starter_detector.onnx"))
    ap.add_argument("--folder", default=str(ROOT / "samples"))
    ap.add_argument("--skip", type=int, default=0, help="frames skipped between inferences")
    ap.add_argument("--conf", type=float, default=0.35)
    a = ap.parse_args()
    reg = ModelRegistry()
    reg.load(a.model, conf_threshold=a.conf)
    rows = evaluate_folder(reg, Path(a.folder), a.skip, Path(a.folder) / "accuracy_report.csv")
    print()
    print(f"{'video':28s} {'class':8s} {'true':>5s} {'count':>5s} {'flag':>4s} {'acc%':>6s}")
    for r in rows:
        print(f"{r['video']:28s} {r['class']:8s} {r['true_net']!s:>5s} {r['counted_net']!s:>5s} {r['flagged']!s:>4s} {r['accuracy_pct']:>6}")

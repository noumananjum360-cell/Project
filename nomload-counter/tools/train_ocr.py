"""Train the bundled plate OCR model: python tools/train_ocr.py"""
import os
import sys
from pathlib import Path

if os.name != "nt":  # Windows renders off-screen natively with its system fonts

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nomload.training.ocr_train import train_and_export  # noqa: E402

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    train_and_export(str(ROOT / "models" / "plate_ocr.onnx"), n_plates=n)

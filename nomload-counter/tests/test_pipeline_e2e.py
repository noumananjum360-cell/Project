"""End-to-end: synthetic sample video -> detector -> tracker -> counter vs answer key."""
from pathlib import Path

import pytest

from nomload.config import bundled_models_dir, samples_dir

pytestmark = pytest.mark.skipif(not (bundled_models_dir() / "starter_detector.onnx").exists(),
                                reason="starter model not built")


def test_flour_mill_sample_accuracy():
    from nomload.core.detector import ModelRegistry
    from nomload.services.evaluation import evaluate_folder
    reg = ModelRegistry()
    reg.load(bundled_models_dir() / "starter_detector.onnx")
    rows = evaluate_folder(reg, samples_dir(), 0, log=lambda *_: None)
    overall = [r for r in rows if r["class"] == "ALL"]
    assert overall
    for r in overall:
        assert r["accuracy_pct"] >= 90, r


def test_synthetic_answer_key_consistent():
    from nomload.training.synth import build_scene
    s = build_scene(42, duration=30, recipe="bags")
    key = s.answer_key()
    assert sum(v["in"] for v in key.values()) > 0

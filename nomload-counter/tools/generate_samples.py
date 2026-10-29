"""Generate sample test videos + answer key.

    python tools/generate_samples.py [--out samples]

Creates synthetic loading-bay videos (bags on head/shoulder/back, stacked
cartons, trolleys, conveyor, crowded crossings, pauses on the line and items
carried back out) plus answer_key.csv with the true per-product counts, a
plate-camera clip and a gate pass CSV that matches the samples.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if os.name != "nt":  # Windows renders off-screen natively with its system fonts

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nomload.training.synth import LINE_X, W, build_scene, write_answer_key, write_plate_video, write_video  # noqa: E402

SAMPLES = [
    # file, seed, recipe, duration, density
    ("flour_mill_bay.mp4", 7001, "bags", 60, 1.0),
    ("fmcg_cartons_bay.mp4", 7002, "cartons", 60, 1.0),
    ("beverage_conveyor_bay.mp4", 7003, "conveyor", 60, 1.0),
    ("mixed_busy_bay.mp4", 7004, "mixed", 60, 1.5),
]
PLATE = ("plate_cam_LES-4721.mp4", 7100, "LES-4721", "Punjab")


def compress(path: Path):
    """Transcode to H.264 with ffmpeg when available (10x smaller than mp4v)."""
    if not shutil.which("ffmpeg"):
        return
    tmp = path.with_suffix(".h264.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-c:v", "libx264", "-crf", "26",
                        "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)])
    if r.returncode == 0 and tmp.exists():
        tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "samples"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    calib = {}
    for name, seed, recipe, dur, dens in SAMPLES:
        sc = build_scene(seed, duration=dur, recipe=recipe, density=dens, plate_text="LES-4721")
        n = write_video(sc, out / name)
        compress(out / name)
        key = sc.answer_key()
        for prod, d in sorted(key.items()):
            rows.append({"video": name, "product": prod, "class": d["class"], "true_in": d["in"],
                         "true_out": d["out"], "true_net": d["in"] - d["out"]})
        calib[name] = {"mode": "line", "p1": [LINE_X / W, 0.12], "p2": [LINE_X / W, 0.99], "in_side": 1}
        print(f"{name}: {n} frames, truth {key}")
    write_answer_key(rows, out / "answer_key.csv")
    (out / "calibration.json").write_text(json.dumps(calib, indent=2))
    write_plate_video(out / PLATE[0], PLATE[1], PLATE[2], PLATE[3])
    compress(out / PLATE[0])
    # a gate pass file matching the sample truck
    with open(out / "gate_passes_sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["gate_pass", "vehicle", "customer", "driver", "phone", "destination", "product", "quantity"])
        for r in rows:
            if r["video"] == "flour_mill_bay.mp4":
                w.writerow(["GP-1001", "LES-4721", "Al-Madina Traders", "Aslam", "0300-1234567", "Multan",
                            r["product"], r["true_net"]])
            if r["video"] == "fmcg_cartons_bay.mp4":
                w.writerow(["GP-1002", "TLA-552", "City Distributors", "Rafiq", "", "Hyderabad", r["product"],
                            r["true_net"]])
    print("wrote", out)


if __name__ == "__main__":
    main()

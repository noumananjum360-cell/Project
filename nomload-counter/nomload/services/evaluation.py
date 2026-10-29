"""End-to-end counting accuracy evaluation against an answer-key CSV."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import cv2

from nomload.core.detector import ModelRegistry
from nomload.core.geometry import CountGeometry
from nomload.core.pipeline import CountingEngine, EngineConfig


def run_video(registry: ModelRegistry, video: Path, geometry: CountGeometry, frame_skip: int = 0,
              max_frames: int | None = None, review_threshold: float = 0.45, progress=None) -> dict:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    eng = CountingEngine(registry, geometry, EngineConfig(review_threshold=review_threshold))
    i = 0
    events = []
    infer = []
    t0 = time.time()
    while True:
        ok, fr = cap.read()
        if not ok or (max_frames and i >= max_frames):
            break
        if i % (frame_skip + 1) == 0:
            res = eng.process(fr, ts=i / fps)
            infer.append(res.infer_ms)
            events += res.events
        i += 1
        if progress and i % 50 == 0:
            progress(i, n_total)
    cap.release()
    per_cls: dict[str, dict] = {}
    for e in events:
        d = per_cls.setdefault(e.cls, {"in": 0, "out": 0, "flagged": 0})
        d["in" if e.direction > 0 else "out"] += 1
        d["flagged"] += int(e.flagged)
    wall = time.time() - t0
    return {"video": video.name, "frames": i, "per_class": per_cls, "events": len(events),
            "mean_infer_ms": round(sum(infer) / max(1, len(infer)), 1),
            "processing_fps": round(i / max(wall, 1e-6), 1), "video_fps": fps}


def load_answer_key(path: Path) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = out.setdefault(r["video"], {})
            c = v.setdefault(r["class"], {"in": 0, "out": 0, "net": 0, "products": []})
            c["in"] += int(r["true_in"])
            c["out"] += int(r["true_out"])
            c["net"] += int(r["true_net"])
            c["products"].append(r["product"])
    return out


def evaluate_folder(registry: ModelRegistry, folder: Path, frame_skip: int = 0, out_csv: Path | None = None,
                    log=print) -> list[dict]:
    key = load_answer_key(folder / "answer_key.csv")
    calib = json.loads((folder / "calibration.json").read_text()) if (folder / "calibration.json").exists() else {}
    rows = []
    for video, classes in key.items():
        path = folder / video
        if not path.exists():
            log(f"missing {video}")
            continue
        geo = CountGeometry.from_dict(calib.get(video))
        res = run_video(registry, path, geo, frame_skip)
        tot_true = tot_err = 0
        for cls, truth in classes.items():
            got = res["per_class"].get(cls, {"in": 0, "out": 0, "flagged": 0})
            net = got["in"] - got["out"]
            err = abs(net - truth["net"])
            tot_true += truth["net"]
            tot_err += err
            rows.append({"video": video, "class": cls, "true_net": truth["net"], "counted_net": net,
                         "true_in": truth["in"], "counted_in": got["in"], "true_out": truth["out"],
                         "counted_out": got["out"], "flagged": got["flagged"], "abs_error": err,
                         "accuracy_pct": round(100 * (1 - err / max(1, truth["net"])), 1)})
        for cls, got in res["per_class"].items():
            if cls not in classes:
                net = got["in"] - got["out"]
                tot_err += abs(net)
                rows.append({"video": video, "class": cls, "true_net": 0, "counted_net": net, "true_in": 0,
                             "counted_in": got["in"], "true_out": 0, "counted_out": got["out"],
                             "flagged": got["flagged"], "abs_error": abs(net), "accuracy_pct": 0.0})
        acc = round(100 * (1 - tot_err / max(1, tot_true)), 1)
        rows.append({"video": video, "class": "ALL", "true_net": tot_true,
                     "counted_net": sum(r["counted_net"] for r in rows if r["video"] == video and r["class"] != "ALL"),
                     "true_in": "", "counted_in": "", "true_out": "", "counted_out": "", "flagged": "",
                     "abs_error": tot_err, "accuracy_pct": acc})
        log(f"{video}: accuracy {acc}%  (true {tot_true}, error {tot_err}) "
            f"{res['processing_fps']} fps, {res['mean_infer_ms']} ms/inference")
    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return rows

"""End-to-end self test (``NomLoad.exe --selftest``).

Runs in a throw-away data folder and exercises the real code paths: database
and integrity triggers, users/PIN, licensing, ONNX detector + OCR, the full bay
runtime on a sample video (camera thread -> detection -> tracking -> counting ->
session -> evidence), gate pass matching, reports, Excel, evidence pack and
hash verification. Exit code 0 = all checks passed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path


def run_selftest(report_path: str | None = None) -> int:
    tmp = tempfile.mkdtemp(prefix="nomload_selftest_")
    os.environ["NOMLOAD_HOME"] = tmp
    if os.name != "nt":  # Windows renders off-screen natively with its system fonts
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    results: list[tuple[str, bool, str]] = []
    t_start = time.time()

    def check(name, fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.time() - t0:.1f}s)"))
        except Exception as e:
            results.append((name, False, f"{e}\n{traceback.format_exc(limit=3)}"))
        ok = results[-1][1]
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {results[-1][2].splitlines()[0]}", flush=True)
        return ok

    from nomload import __version__
    from nomload.config import samples_dir
    from nomload.services.app import AppServices
    print(f"NomLoad Counter {__version__} self-test (data: {tmp})")
    ctx: dict = {}

    def t_db():
        app = AppServices()
        ctx["app"] = app
        import sqlite3
        try:
            app.db.execute("DELETE FROM audit_log")
            raise AssertionError("audit log delete was not blocked")
        except sqlite3.DatabaseError:
            pass
        return "schema + append-only triggers OK"

    def t_auth():
        app = ctx["app"]
        u = app.auth.login("admin", "admin123")
        app.user = u
        sup = app.auth.verify_supervisor("admin", "1234")
        assert sup.can("approve_mismatch")
        return "default admin login + supervisor PIN OK"

    def t_license():
        st = ctx["app"].license.status()
        assert st.usable, st.message
        return st.label

    def t_models():
        app = ctx["app"]
        app.load_models()
        det = app.registry.detector
        assert det is not None
        assert app.ocr is not None, "plate OCR model missing"
        return f"{det.name} [{det.format}] providers={det.providers}"

    def t_plate():
        import cv2
        app = ctx["app"]
        from nomload.core.plates import PlateReader
        cap = cv2.VideoCapture(str(samples_dir() / "plate_cam_LES-4721.mp4"))
        r = PlateReader(app.ocr)
        i = 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if i % 3 == 0 and i > 45:
                det = app.registry.detector
                dets = [d for d in det.detect(fr) if d.cls == "plate"] if "plate" in det.classes else None
                r.add(r.read_frame(fr, None, dets))
            i += 1
        best = r.best()
        assert best and best.text == "LES-4721", f"read {best.text if best else None}"
        return f"{best.text} ({best.confidence:.0%})"

    def t_session():
        app = ctx["app"]
        from nomload.core.geometry import CountGeometry
        from nomload.core.video import SourceSpec
        from nomload.services.evaluation import load_answer_key
        import json
        video = samples_dir() / "flour_mill_bay.mp4"
        calib = json.loads((samples_dir() / "calibration.json").read_text())[video.name]
        bid = app.bays.save_bay(app.user, "Bay 1")
        app.bays.save_camera(app.user, bid, "Bay 1 counting", "count",
                             SourceSpec("file", str(video), loop=False, realtime=False), CountGeometry.from_dict(calib))
        truth = load_answer_key(samples_dir() / "answer_key.csv")[video.name]["bag"]["net"]
        flour = app.products.by_name("Flour 50kg bag")
        gid = app.gate_passes.create(app.user, "GP-TEST-1", [(flour.id, truth)], "LES-4721", "Self-test Traders")
        from nomload.services.runtime import BayRuntime
        bay = app.bays.get(bid)
        rt = BayRuntime(app, bay)
        app.runtimes[bid] = rt
        sid = rt.start_session(app.user, gid)
        rt.start()
        t0 = time.time()
        last, last_t = -1, time.time()
        while not rt.src.ended:
            time.sleep(0.5)
            if rt.src.frames_read != last:
                last, last_t = rt.src.frames_read, time.time()
            if not rt.is_alive():
                raise RuntimeError("bay processing thread stopped unexpectedly")
            if time.time() - last_t > 60 or time.time() - t0 > 900:
                rt.shutdown()
                raise RuntimeError(f"video processing stalled after {rt.src.frames_read} frames")
        time.sleep(1.5)
        s = rt.close_session(app.user)
        rt.shutdown()
        ctx["sid"] = sid
        counted = s.total_counted + s.total_pending
        err = abs(counted - truth)
        assert err <= max(1, round(truth * 0.05)), f"counted {counted} vs true {truth}"
        return f"counted {s.total_counted} (+{s.total_pending} to review) vs true {truth}; status {s.status}"

    def t_reports():
        import datetime as dt
        app = ctx["app"]
        out = Path(tmp) / "reports"
        out.mkdir(exist_ok=True)
        app.reports.loading_certificate(ctx["sid"], out / "cert.pdf")
        app.reports.daily_dispatch(dt.date.today(), out / "daily.pdf")
        app.reports.mismatch_report(dt.date.today(), dt.date.today(), out / "mismatch.pdf")
        app.reports.export_excel(dt.date.today(), dt.date.today(), out / "export.xlsx")
        for f in ("cert.pdf", "daily.pdf", "mismatch.pdf", "export.xlsx"):
            assert (out / f).stat().st_size > 1000, f
        return "certificate, daily, mismatch PDFs + Excel"

    def t_evidence():
        app = ctx["app"]
        from nomload.services import evidence
        res = evidence.verify_session(app.db, ctx["sid"])
        assert res and all(r["status"] == "ok" for r in res), res
        kinds = {r["kind"] for r in res}
        assert "clip" in kinds and "snapshot" in kinds, kinds
        z = evidence.build_evidence_pack(app.db, ctx["sid"], Path(tmp) / "pack.zip")
        assert z.stat().st_size > 10000
        return f"{len(res)} files hashed & verified, evidence pack {z.stat().st_size // 1024} KB"

    for name, fn in (("Database & integrity", t_db), ("Users & PIN", t_auth), ("Licensing", t_license),
                     ("AI models", t_models), ("Number plate OCR", t_plate), ("Loading session end-to-end", t_session),
                     ("Reports & Excel", t_reports), ("Evidence integrity", t_evidence)):
        if not check(name, fn) and name in ("Database & integrity", "Users & PIN", "AI models"):
            break
    ok = all(r[1] for r in results) and len(results) == 8
    lines = [f"NomLoad Counter {__version__} self-test - {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Python {sys.version.split()[0]} on {sys.platform}", ""]
    lines += [f"{'PASS' if r[1] else 'FAIL'}  {r[0]}: {r[2]}" for r in results]
    lines += ["", f"RESULT: {'ALL PASSED' if ok else 'FAILED'} in {time.time() - t_start:.0f}s"]
    text = "\n".join(lines)
    print("\n" + text)
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    try:
        ctx.get("app") and ctx["app"].shutdown()
    except Exception:
        pass
    return 0 if ok else 1

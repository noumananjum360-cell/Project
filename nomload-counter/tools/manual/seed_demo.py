"""Seed a demo database for the manual by running REAL loading sessions through the bay runtime."""
import os, sys, time, json, csv, shutil
from pathlib import Path
R = str(Path(__file__).resolve().parents[2])
M = os.environ.get("NOMLOAD_MANUAL_WORK", R + "/build/manual_work")
os.makedirs(M, exist_ok=True)
HOME = M + "/home"
if os.path.exists(HOME):
    shutil.rmtree(HOME)
os.environ["NOMLOAD_HOME"] = HOME
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["NOMLOAD_FINGERPRINT"] = "manual-demo-pc"
sys.path.insert(0, R)
from nomload.services.app import AppServices
from nomload.core.video import SourceSpec
from nomload.core.geometry import CountGeometry
from nomload.services.runtime import BayRuntime
S = R + "/samples"
cal = json.load(open(S + "/calibration.json"))
app = AppServices()
u = app.auth.login("admin", "admin123")
app.user = u
app.db.execute("UPDATE users SET full_name='Muhammad Nouman', must_change_pw=0 WHERE id=?", (u.id,))
u = app.auth.login("admin", "admin123"); app.user = u
app.auth.create_user("supervisor", "super123", "supervisor", "Imran Shah", pin="4321", actor=u)
app.auth.create_user("clerk", "clerk123", "clerk", "Bilal Ahmed", actor=u)
app.db.execute("UPDATE users SET must_change_pw=0")
s = app.settings
s.set("company_name", "Al-Noor Flour & Foods (Pvt) Ltd")
s.set("company_address", "Plot 14, Sundar Industrial Estate, Lahore  ·  042-111-000-111")
s.set("tolerance_units", 1)
# demo licence (only when the vendor private key is present on this PC)
priv = Path(R) / "tools" / "vendor_keys" / "vendor_private.pem"
if priv.exists():
    from cryptography.hazmat.primitives import serialization
    from nomload.licensing.license import make_key
    k = make_key(serialization.load_pem_private_key(priv.read_bytes(), None), 2, 999999)
    print(app.license.activate(k).label)
app.load_models()

def geo(v, roi=None):
    g = CountGeometry.from_dict(cal[v])
    g.plate_roi = roi
    return g

b1 = app.bays.save_bay(u, "Bay 1 - Flour")
c1 = app.bays.save_camera(u, b1, "Bay 1 counting cam", "count", SourceSpec("file", S + "/flour_mill_bay.mp4", False, False), geo("flour_mill_bay.mp4"))
p1 = app.bays.save_camera(u, b1, "Bay 1 plate cam", "plate", SourceSpec("file", S + "/plate_cam_LES-4721.mp4", True, False))
b2 = app.bays.save_bay(u, "Bay 2 - FMCG", auto_session=False)
c2 = app.bays.save_camera(u, b2, "Bay 2 counting cam", "count", SourceSpec("file", S + "/fmcg_cartons_bay.mp4", False, False), geo("fmcg_cartons_bay.mp4"))
# reference frames for tamper detection
import cv2
for cid, v in ((c1, "flour_mill_bay.mp4"), (c2, "fmcg_cartons_bay.mp4")):
    cap = cv2.VideoCapture(S + "/" + v); ok, fr = cap.read(); cap.release()
    app.bays.save_calibration(u, cid, app.bays.get(b1 if cid == c1 else b2).count_camera.geometry, fr)

P = {p.name: p.id for p in app.products.list()}
gp = app.gate_passes
gp.import_file(u, S + "/gate_passes_sample.csv")
g3 = gp.create(u, "GP-1003", [(P["Flour 50kg bag"], 30)], "RIK-908", "Shah Jee Distributors", "Kamran", "0321-5550001", "Rawalpindi")
g4 = gp.create(u, "GP-1004", [(P["Carton 1.5L x6"], 45), (P["Shrink pack 500ml x12"], 30)], "BKF-456", "Karachi Cash & Carry", "Saleem", "", "Karachi")
gp.create(u, "GP-1005", [(P["Flour 50kg bag"], 400), (P["Sugar 50kg bag"], 100)], "LEA-1234", "Al-Madina Traders", "Aslam", "0300-1234567", "Multan")
gp.create(u, "GP-1006", [(P["Cement 50kg bag"], 600)], "TLB-990", "Bismillah Builders", "Nadeem", "", "Hyderabad")
gp.create(u, "GP-1007", [(P["Beverage crate x24"], 120)], "ICT-1234", "Capital Beverages", "Usman", "", "Islamabad")

sup = app.auth.verify_supervisor("supervisor", "4321")

def run(bay_id, gate_number, video=None, review=True, close_user=u):
    bay = app.bays.get(bay_id)
    if video:
        bay.count_camera.source = SourceSpec("file", S + "/" + video, False, False)
    rt = BayRuntime(app, bay)
    app.runtimes[bay_id] = rt
    g = gp.by_number(gate_number)
    sid = rt.start_session(u, g.id if g else None)
    rt.start()
    t0 = time.time()
    while not rt.src.ended and time.time() - t0 < 300:
        time.sleep(0.3)
    time.sleep(1.5)
    if review:
        for e in app.sessions.pending_events(sid):
            app.sessions.review_event(e["id"], True, sup)
    summ = rt.close_session(close_user)
    rt.shutdown(); time.sleep(0.5)
    app.runtimes.pop(bay_id, None)
    print(round(time.time()-t0,1), "s", rt.src.frames_read, "frames", gate_number, summ.status, summ.total_counted, "/", summ.total_expected, "plate", summ.plate_text)
    return sid, summ

sid1, s1 = run(b1, "GP-1001")
sid2, s2 = run(b2, "GP-1002")
if not s2.plate_text:
    app.sessions.set_plate(sid2, "TLA-552", 1.0, None, u, corrected=True)
sid3, s3 = run(b1, "GP-1003")
if s3.status == "mismatch":
    app.sessions.release(sid3, sup, "5 bags short - stock finished. Customer informed; balance goes on tomorrow's trip.")
    app.alerts.raise_alert("session_released", f"Session #{sid3} released by Imran Shah", b1, sid3)
sid4, s4 = run(b2, "GP-1004", video="mixed_busy_bay.mp4")
if not s4.plate_text:
    app.sessions.set_plate(sid4, "BKF-456", 1.0, None, u, corrected=True)
# spread the sessions over recent days/hours for the dashboard
day = 86400
now = time.time()
shift = {sid1: -2 * day - 3 * 3600, sid2: -1 * day - 5 * 3600, sid3: -2 * 3600, sid4: -1 * 3600}
for sid, d in shift.items():
    app.db.execute("UPDATE sessions SET started_at=started_at+?, ended_at=ended_at+? WHERE id=?", (d, d, sid))
    app.db.execute("UPDATE count_events SET ts=ts+? WHERE session_id=?", (d, sid))
# camera definitions for the live screenshots: realtime + looping
app.bays.save_camera(u, b1, "Bay 1 counting cam", "count", SourceSpec("file", S + "/flour_mill_bay.mp4", True, True), app.bays.get(b1).count_camera.geometry, c1)
app.bays.save_camera(u, b1, "Bay 1 plate cam", "plate", SourceSpec("file", S + "/plate_cam_LES-4721.mp4", True, True), None, p1)
app.bays.save_camera(u, b2, "Bay 2 counting cam", "count", SourceSpec("file", S + "/fmcg_cartons_bay.mp4", True, True), app.bays.get(b2).count_camera.geometry, c2)
json.dump({"sids": [sid1, sid2, sid3, sid4], "b1": b1, "b2": b2}, open(M + "/seed.json", "w"))
app.shutdown()
print("seeded", HOME)

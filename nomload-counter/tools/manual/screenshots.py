"""Drive the real NomLoad app and save the screenshots used in the user manual."""
import os, sys, json, time
from pathlib import Path
R = str(Path(__file__).resolve().parents[2])
M = os.environ.get("NOMLOAD_MANUAL_WORK", R + "/build/manual_work")
os.environ["NOMLOAD_HOME"] = M + "/home"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["NOMLOAD_FINGERPRINT"] = "manual-demo-pc"
sys.path.insert(0, R)
OUT = M + "/img"
os.makedirs(OUT, exist_ok=True)
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
qapp = QApplication(sys.argv)
f = QFont("Inter"); f.setPixelSize(14); qapp.setFont(f)
from PySide6.QtWidgets import QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
from nomload import theme
from nomload.services.app import AppServices
app = AppServices()
app.settings.set("sound_alerts", False)
theme.set_mode("light")
qapp.setStyleSheet(theme.stylesheet())
app.load_models()
seed = json.load(open(M + "/seed.json"))
sids = seed["sids"]
from nomload.ui.main_window import MainWindow
from nomload.ui import dialogs as D
W = MainWindow(app)
W.resize(1440, 900)
W.show()

def save(w, name):
    qapp.processEvents()
    w.grab().save(f"{OUT}/{name}.png")
    print("shot", name, flush=True)

def show_dialog(d, name, w=None, h=None):
    d.show(); qapp.processEvents()
    if w: d.resize(w, h)
    qapp.processEvents(); time.sleep(0.2); qapp.processEvents()
    save(d, name); d.close()

steps = []
def step(delay=400):
    def deco(fn):
        steps.append((fn, delay)); return fn
    return deco

@step()
def s_splash():
    from nomload.ui.login import make_splash
    sp = make_splash(); save(sp, "01_splash")

@step()
def s_login():
    W.login.user.setText("admin"); W.login.pw.setText("••••••")
    save(W.login, "02_login")
    W.login.pw.setText("admin123"); W.login._login()

@step(1500)
def s_dash():
    for t in list(W.toasts.parentWidget().findChildren(type(W.toasts.itemAt(0).widget()))) if W.toasts.count() else []:
        t.deleteLater()
    W.go("dashboard"); W.pages["dashboard"].refresh(); save(W, "03_dashboard")

@step(200)
def s_live_start():
    P = {p.name: p.id for p in app.products.list()}
    g8 = app.gate_passes.create(app.user, "GP-1008", [(P["Carton 1.5L x6"], 40), (P["Shrink pack 500ml x12"], 32)],
                                "TLA-552", "City Distributors", "Rafiq", "", "Hyderabad")
    b1, b2 = seed["b1"], seed["b2"]
    app.runtimes[b1].start_session(app.user, app.gate_passes.by_number("GP-1005").id)
    app.runtimes[b2].start_session(app.user, g8)
    W.go("live")

@step(14000)
def s_live():
    save(W, "04_live_bays")

@step(600)
def s_live_focus():
    lp = W.pages["live"]
    lp.focus_bay(list(lp.widgets.values())[0])

@step(3000)
def s_live_focus_shot():
    save(W, "05_live_single_bay")
    lp = W.pages["live"]; lp.focus_bay(None)

@step()
def s_picker():
    show_dialog(D.GatePassPicker(W, app), "06_gate_pass_picker", 900, 560)

@step()
def s_plate():
    s = app.sessions.summary(sids[0])
    show_dialog(D.PlateDialog(W, s.plate_text, s.plate_image), "07_plate_correct")

@step()
def s_sup():
    d = D.SupervisorDialog(W, app, "Release this truck although the quantity does not match?", need_reason=True)
    d.user.setCurrentText("supervisor"); d.pin.setText("4321")
    d.reason.setPlainText("2 cartons short - customer informed, will be added to the next trip.")
    show_dialog(d, "08_supervisor_approval")

@step()
def s_results():
    show_dialog(D.SessionResultDialog(W, app, app.sessions.summary(sids[0])), "09_result_cleared")
    show_dialog(D.SessionResultDialog(W, app, app.sessions.summary(sids[1])), "10_result_mismatch")

@step()
def s_review():
    live_sids = [rt.session_id for rt in app.runtimes.values() if rt.session_id]
    pend = [s for s in live_sids if app.sessions.pending_events(s)]
    if pend:
        sup = app.auth.verify_supervisor("supervisor", "4321")
        show_dialog(D.ReviewDialog(W, app, pend[0], sup), "11_review_counts", 980, 640)

@step()
def s_sessions():
    W.go("sessions"); sp = W.pages["sessions"]; sp.tabs.setCurrentIndex(0); sp.refresh(); save(W, "12_sessions_gate_passes")
    sp.tabs.setCurrentIndex(1); sp.refresh(); save(W, "13_sessions_today")
    d = D.GatePassDialog(W, app)
    d.number.setText("GP-1010"); d.vehicle.setText("LEB-2231"); d.customer.setText("Sialkot Traders")
    d.driver.setText("Arif"); d.phone.setText("0333-4445566"); d.dest.setText("Sialkot")
    d.rows[0][1].setValue(350); d._add_row(); d.rows[1][0].setCurrentIndex(3); d.rows[1][1].setValue(80)
    show_dialog(d, "14_new_gate_pass", 700, 640)

@step()
def s_history():
    W.go("history"); hp = W.pages["history"]
    from PySide6.QtCore import QDate
    hp.d0.setDate(QDate.currentDate().addDays(-7)); hp.search(); save(W, "15_history")
    from nomload.ui.pages.history import SessionDetailDialog
    d = SessionDetailDialog(W, app, sids[2], W)
    d.show(); d.resize(1150, 760); qapp.processEvents()
    save(d, "16_session_summary")
    d.tabs.setCurrentIndex(1); save(d, "17_session_snapshots")
    from nomload.services import evidence
    d._verified(evidence.verify_session(app.db, sids[2])); d.tabs.setCurrentIndex(3); save(d, "18_session_evidence")
    d.tabs.setCurrentIndex(4); save(d, "19_session_audit")
    d.close()

@step()
def s_reports():
    W.go("reports"); save(W, "20_reports")
    import datetime as dt
    rp = M + "/pdf"; os.makedirs(rp, exist_ok=True)
    app.reports.loading_certificate(sids[0], rp + "/certificate.pdf")
    app.reports.daily_dispatch(dt.date.today(), rp + "/daily.pdf")
    app.reports.mismatch_report(dt.date.today() - dt.timedelta(days=7), dt.date.today(), rp + "/mismatch.pdf")

@step()
def s_products():
    W.go("products"); pp = W.pages["products"]; pp.table.selectRow(5); save(W, "21_products")

@step()
def s_cameras():
    W.go("cameras"); save(W, "22_cameras")
    from nomload.ui.pages.cameras import CameraDialog, CalibrationDialog
    d = CameraDialog(W, app, seed["b1"])
    d.name.setText("Bay 1 counting cam"); d.kind.setCurrentIndex(0); d.brand.setCurrentText("Hikvision")
    d.ip.setText("192.168.1.64"); d.user.setText("admin"); d.pw.setText("secret"); d.sub.setChecked(True)
    d.test_msg.setText("✔ Connected: 1280x720 @ 25 fps")
    d.test_msg.setStyleSheet(f"color:{theme.c('success')}; font-weight:600;")
    import cv2
    from nomload.ui.widgets import bgr_to_qimage
    from PySide6.QtGui import QPixmap
    cap = cv2.VideoCapture(R + "/samples/flour_mill_bay.mp4"); cap.set(1, 120); ok, fr = cap.read()
    d.preview.setPixmap(QPixmap.fromImage(bgr_to_qimage(fr)).scaledToHeight(220))
    show_dialog(d, "23_add_camera_rtsp", 680, 860)
    cam = app.bays.get(seed["b1"]).count_camera
    cd = CalibrationDialog(W, app, cam, (True, fr, "ok"))
    cd.show(); cd.resize(1200, 820); qapp.processEvents(); save(cd, "24_calibration"); cd.close()

@step()
def s_training():
    from nomload.training.dataset import Dataset, add_synthetic
    ds = Dataset.create("al_noor_bay1")
    if ds.stats()["images"] == 0:
        add_synthetic(ds, 40, seed=77)
    W.go("training"); tp = W.pages["training"]; tp.reload_datasets("al_noor_bay1")
    tp.tabs.setCurrentIndex(0); save(W, "25_training_collect")
    tp.tabs.setCurrentIndex(1); tp.reload_images(); tp.img_list.setCurrentRow(5); qapp.processEvents(); save(W, "26_training_annotate")
    tp.tabs.setCurrentIndex(2)
    tp.train_log.setPlainText("Built-in trainer: 34 training images, classes ['bag', 'carton', 'crate', 'pack', 'person', 'truck', 'plate']\n"
                              + "\n".join(f"iteration {i}/1500  loss {0.9*0.996**i+0.25:.4f}" for i in range(25, 700, 25)))
    for i in range(25, 700, 25):
        tp._train_progress(i, 1500, 0.9 * 0.996 ** i + 0.25)
    save(W, "27_training_train")
    tp.tabs.setCurrentIndex(3); tp.reload_models(); save(W, "28_training_models")

@step()
def s_users():
    W.go("users"); save(W, "29_users")
    rows = app.auth.users()
    show_dialog(D.UserDialog(W, app, [r for r in rows if r["username"] == "clerk"][0]), "30_edit_user")

@step()
def s_settings():
    W.go("settings"); sp = W.pages["settings"]; qapp.processEvents()
    host = sp.findChild(type(sp), None) if False else sp.layout().itemAt(0).widget().widget()
    host.resize(1170, host.sizeHint().height()); qapp.processEvents()
    host.grab().save(f"{OUT}/31_settings_full.png"); print("shot settings full")
    save(W, "32_settings_top")

@step()
def s_alerts():
    show_dialog(D.AlertsDialog(W, app), "33_alerts", 1000, 620)
    show_dialog(D.ChangePasswordDialog(W, app), "34_change_password")

@step()
def s_dark():
    W.toggle_theme(); W.go("live")

@step(5000)
def s_dark_shot():
    save(W, "35_dark_live")
    W.go("dashboard"); W.pages["dashboard"].refresh(); save(W, "36_dark_dashboard")
    W.toggle_theme()

@step()
def s_compact():
    W.resize(1366, 768); W.go("live")

@step(4000)
def s_compact_shot():
    save(W, "37_live_1366")

@step()
def s_end():
    app.shutdown(); qapp.quit()

def run(i=0):
    if i >= len(steps):
        return
    fn, delay = steps[i]
    try:
        fn()
    except Exception:
        import traceback; traceback.print_exc()
    QTimer.singleShot(delay, lambda: run(i + 1))

QTimer.singleShot(800, run)
qapp.exec()
print("done")

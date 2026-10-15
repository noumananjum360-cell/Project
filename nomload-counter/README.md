# NomLoad Counter

**Devnom product family** · Offline Windows desktop app that counts bags and cartons being loaded onto
trucks from existing CCTV cameras, reads the truck's number plate, and matches the counted quantity
against the gate pass / invoice. Any mismatch raises an alert **before the truck leaves**, with video
evidence.

Built for flour mills, cement plants, fertilizer and sugar mills, beverage depots, FMCG warehouses and
distributors in Pakistan. It runs 100% offline. The internet is only used for optional WhatsApp, email
and SMS alerts, which are queued and sent later if the PC is offline.

```
Login ─► Live Bays ─► Start loading (gate pass) ─► camera counts every bag/carton ─► Close & verify
                                                                     │
                                  CLEARED (green, truck may leave) ◄─┴─► MISMATCH (red, loud alarm,
                                                                         supervisor PIN + written reason)
```

---

## Contents

1. [Features](#features)
2. [Quick start (from source)](#quick-start-from-source)
3. [Folder structure](#folder-structure)
4. [Camera setup and calibration](#camera-setup-and-calibration)
5. [Running a loading session](#running-a-loading-session)
6. [Training custom products](#training-custom-products)
7. [Number plate recognition](#number-plate-recognition)
8. [Users, roles and security](#users-roles-and-security)
9. [Licensing and the key generator](#licensing-and-the-key-generator)
10. [Building the Windows installer](#building-the-windows-installer)
11. [Testing and accuracy](#testing-and-accuracy)
12. [Performance tuning](#performance-tuning)
13. [Branding and translation](#branding-and-translation)
14. [Known limitations](#known-limitations)

---

## Features

| Area | What it does |
|---|---|
| Video input | RTSP IP cameras/NVRs (Hikvision, Dahua, CP Plus, Uniview, TP-Link, generic ONVIF) with a URL helper and **Test connection**; USB webcams; MP4/AVI files. Auto-reconnect with back-off; alert if a camera is offline longer than *N* seconds. |
| Calibration | Draw a counting **line** or **zone**, the loading **direction arrow**, **ignore zones** and the **plate region** on a live frame. Saves a reference view for tamper detection. |
| Counting | ONNX detector → ByteTrack → direction-aware line counter. IN = +1, carried back OUT = −1. Hysteresis band (pausing on the line never double counts), identity recovery after occlusion or ID switches, class-aware tracking (a labourer can't steal a bag's ID). Units-per-stack rule per product. Per-count confidence; low-confidence counts go to **supervisor review** instead of being silently accepted. A snapshot is saved for every counted item. |
| Tamper | Covered / blurred / moved / view changed, compared with the calibrated reference; must persist for *N* s before alerting. |
| Plates | Plate localisation (detector class `plate` or classical localiser), character OCR (bundled ONNX, or PaddleOCR-rec ONNX), Pakistani format rules (Punjab, Sindh, KP, Balochistan, ICT, commercial `TL?`), letter/digit confusion fixing, multi-frame voting, one-click correction, auto-match to an open gate pass. |
| Sessions | Start from a gate pass, or automatically when a truck is detected. Multiple products per gate pass, each counted separately. Close manually, or automatically when the truck leaves. Tolerance in units and/or %. CLEARED / MISMATCH (+ alarm) / RELEASED (supervisor PIN + reason). |
| Gate passes | Manual entry, CSV/Excel import (multi-row → multi-product), template download, and an `ERPConnector` interface (a folder-drop connector is included). |
| Evidence | Rolling pre-roll buffer per camera, full session clip, per-item snapshots, plate image. Every file is **SHA-256 hashed** in the DB; **Verify evidence** detects edits or deletions. One-click **Evidence Pack** (ZIP: clip + PDF + snapshots + manifest). |
| Alerts | On-screen banners plus alarm/chime/beep sounds. Remote alerts by email (SMTP), WhatsApp (Meta Cloud API) or SMS (HTTP gateway template), held in a persistent outbox; the owner chooses which events are sent. |
| Dashboard & reports | Trucks today, units per product, mismatches, average loading time per bay, busiest hours, insights. PDF loading certificate, daily dispatch summary, mismatch report (company logo, trial watermark). Excel export of sessions, product lines, every count event and alerts. |
| Users | Admin / Supervisor / Clerk, scrypt-hashed passwords and PINs, login lock-out, full **append-only audit log** (enforced by SQLite triggers). Count events, sessions and evidence records cannot be deleted; an Admin can only soft-delete, and that is audited. |
| Licensing | Ed25519-signed offline keys, bound to the first PC (hardware fingerprint), tiers by bays (Starter 1, Professional 4, Enterprise unlimited), machine-locked activation keys via request code, signed revocation lists, 14-day trial with TRIAL watermark, clock-rollback detection, and a **batch key generator** (CLI and GUI). |
| Training | Frame extraction from site video, annotation tool with **auto-label**, one-click fine-tuning (built-in NumPy trainer, or Ultralytics YOLO if installed), ONNX export, precision/recall, accuracy on sample videos, and **hot-swap** into running bays. Product profiles with sample images. Synthetic data generator. |

---

## Quick start (from source)

**Easiest:** install Python 3.11 (64-bit, tick *Add python.exe to PATH*), then double-click
**`START_NOMLOAD.bat`**. The first start installs everything into `.venv` (a few minutes); later starts
open the app directly. If something goes wrong the window stays open and shows the error.

Manual alternative:

```bat
:: Windows, Python 3.11 x64
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Log in with **admin / admin123**. You are asked to change the password on first login. The default
supervisor PIN is **1234**; change it under *Change password*.

Demo in two minutes:

1. **Cameras → Add bay**, then **Add camera** → *Video file* → `samples\flour_mill_bay.mp4`.
2. **Calibrate** → drag the counting line across the truck entrance so that the arrow points **into**
   the truck. Save, then **Apply & restart bays**.
3. Optionally add a second camera with role *Number plate camera* → `samples\plate_cam_LES-4721.mp4`.
4. **Sessions → Import CSV / Excel** → `samples\gate_passes_sample.csv`.
5. **Live Bays → Start loading** → choose `GP-1001` and watch the count. Press **Close & verify**.

The data folder is `%PROGRAMDATA%\Devnom\NomLoad`. It holds the database, evidence, models and logs.
Back it up by copying the folder, or with **Settings → Backup database**. Set `NOMLOAD_HOME` to use a
different folder.

---

## Folder structure

```
nomload-counter/
├─ START_NOMLOAD.bat          double-click to install (first time) and start from source
├─ run.py                     start the app (python run.py | NomLoad.exe --selftest)
├─ nomload/
│  ├─ app.py                  entry point, splash, self-test switch
│  ├─ config.py               paths (data folder, bundled models, samples)
│  ├─ i18n.py                 translation layer (Urdu-ready, RTL aware)
│  ├─ selftest.py             end-to-end self test used on the packaged .exe
│  ├─ theme/theme.json        ALL brand colours + fonts (single file)
│  ├─ assets/                 logo.svg/png, app.ico, wordmark, alarm/chime/beep .wav
│  ├─ core/                   UI-free engine
│  │  ├─ video.py             RTSP/USB/file sources, reconnect, RTSP URL helper, test connection
│  │  ├─ detector.py          ONNX Runtime detectors (built-in format + YOLOv5/v8/v11), hot-swap registry
│  │  ├─ tracker.py           ByteTrack (Kalman + Hungarian, two-stage association)
│  │  ├─ counter.py           direction-aware line/zone counter, double-count prevention, confidence
│  │  ├─ geometry.py          calibrated lines, zones, ignore zones, plate region
│  │  ├─ pipeline.py          detection → tracking → counting + overlay drawing
│  │  ├─ plates.py            plate localisation, segmentation, OCR, voting
│  │  ├─ plate_formats.py     Pakistani plate formats, normalisation, fuzzy matching
│  │  ├─ tamper.py            covered / blurred / moved / changed detection
│  │  └─ recorder.py          rolling buffer, session clip, snapshots
│  ├─ data/                   SQLite schema + triggers, encryption, hashing
│  ├─ services/               sessions, gate passes, products, bays, alerts, evidence, reports,
│  │                          evaluation, per-bay runtime threads, app composition root
│  ├─ licensing/license.py    keys, fingerprint, trial, revocation
│  ├─ training/               synthetic scene generator, NumPy CNN + ONNX export, OCR trainer,
│  │                          datasets (YOLO format), training jobs
│  └─ ui/                     PySide6 UI (login, main window, pages, dialogs, widgets, icons)
├─ models/                    starter_detector.onnx, plate_ocr.onnx
├─ samples/                   synthetic test videos, answer_key.csv, calibration.json, gate pass CSV
├─ tools/                     keygen.py, generate_samples.py, train_starter.py, train_ocr.py,
│                             evaluate.py, make_assets.py
├─ build/                     nomload.spec, keygen.spec, installer.iss, build_windows.bat
└─ tests/                     pytest suite
```

---

## Camera setup and calibration

**Placement.** Mount the counting camera high, looking down at the truck tailgate or loading
platform, so that every labourer passes under it. Avoid pointing it into direct sunlight. A plate
camera is optional; it should see the rear plate at least 150 px wide (most 2 MP cameras manage this at
3–6 m).

**Connecting.** Go to **Cameras → Add camera → IP camera / NVR (RTSP)**, pick the brand, then enter the
IP address, username, password and channel. The URL is built for you. Press **Test connection** to
see a live frame.

| Brand | Main stream | Sub stream |
|---|---|---|
| Hikvision / HiLook | `rtsp://user:pass@IP:554/Streaming/Channels/101` | `.../102` |
| Dahua / CP Plus | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` | `subtype=1` |
| Uniview | `rtsp://user:pass@IP:554/unicast/c1/s0/live` | `s1` |
| Generic ONVIF | `rtsp://user:pass@IP:554/onvif1` (varies by maker) | |

Through an NVR, the channel number selects the camera. On slow PCs use the **sub-stream**. NomLoad
uses RTSP over TCP for reliability on busy factory networks.

**Calibration** (*Cameras → Calibrate*):

* **Counting line**: drag a line across the truck entrance. The amber **arrow must point into the
  truck**; use **Flip direction** if it doesn't. Items crossing in the arrow's direction count +1, and
  items carried back out count −1.
* **Counting zone**: as an alternative to a line, click the corners of the truck bed area and
  double-click to finish. Entering the zone counts +1.
* **Ignore zones**: hide areas such as the stock pile, a walkway or a conveyor return.
* **Plate region**: drag a rectangle where the plate appears.
* **Tolerance band**: the shaded strip around the line. Items must cross the whole strip to count, so
  labourers who stop or sway on the line are never double counted.
* Tick **Save this view as the tamper reference**. NomLoad then alerts if the camera is covered,
  blurred, moved or pointed elsewhere.

---

## Running a loading session

1. **Live Bays → Start loading**, then pick the gate pass. Alternatively, enable *auto start* on the bay
   so a session opens when a truck is detected, and link the gate pass later.
2. The bay screen shows the video with the counting line and tracked items (`bag #12`), the **big
   counter against expected**, a progress bar, the plate, the gate pass and elapsed time. If one gate
   pass has two products that look alike (for example two bag types), the clerk selects the product
   being loaded with the radio buttons.
3. A count with low confidence appears as "⚠ needs review". A supervisor accepts or rejects it after
   checking the snapshot (**Review**).
4. **Close & verify**. Closing also happens automatically when the truck leaves, if enabled.
   * **CLEARED**: every product is within tolerance. A chime plays and the truck may leave.
   * **MISMATCH**: a loud alarm sounds and the truck stays on hold. A **supervisor** must enter their
     PIN and a written reason to release it. Everything is recorded in the audit log.
5. **History** finds any truck by date, plate, gate pass, product, bay or status. From there you can play
   the clip, **Verify evidence** (re-hash all files), export an **Evidence pack**, or print the
   **loading certificate**.

**Gate pass import format** (CSV or .xlsx; one row per product):

```csv
gate_pass,vehicle,customer,driver,phone,destination,product,quantity
GP-1001,LES-4721,Al-Madina Traders,Aslam,0300-1234567,Multan,Flour 50kg bag,400
GP-1001,LES-4721,Al-Madina Traders,Aslam,0300-1234567,Multan,Sugar 50kg bag,100
```

**ERP integration.** Subclass `nomload.services.catalog.ERPConnector`, implement
`fetch_open_gate_passes()` (and optionally `push_result()`), then register the class in `CONNECTORS`. A
`FolderDropConnector` that picks up CSV files an ERP exports to a shared folder is included.

---

## Training custom products

Every factory's bags and cartons look different. The starter model is trained only on synthetic
scenes, which is enough for demos. **Train on the customer's own footage before going live.**

1. **Collect frames.** Export 10–30 minutes of real loading from the NVR as MP4. In **Training → 1
   Collect frames**, choose the video. NomLoad takes every Nth frame and skips near-duplicates. Aim
   for 200–500 frames covering day and night, different labourers, head, shoulder and arm carrying,
   and trolleys.
2. **Annotate.** Draw a box around every countable item (and people and trucks if you want them
   detected). Keys **1–9** switch class, **Delete** or right-click removes a box, and **PgDn** saves and
   moves to the next image. **Auto-label** pre-fills boxes with the current model, so you only correct
   them. Use **Add class** for site-specific classes such as `cement_bag_red` or `carton_1L`.
3. **Train.** Choose **Built-in trainer (CPU)** and about 1500 iterations (roughly 12 minutes on a Core
   i5), with *Start from the current model* ticked. If Ultralytics is installed
   (`pip install -r requirements-train.txt`), a full YOLO model can be trained instead.
4. **Evaluate and activate.** Check precision and recall, optionally run **Measure counting accuracy on
   sample videos**, then press **Activate**. Every running bay switches to the new model immediately
   (hot-swap, no restart). Older models stay listed for rollback.
5. **Products**: set each product's *detector class*, the **units per detection** stack rule (for
   example a shrink pack of 12 = 12 units, or 1 if the gate pass counts packs), an optional per-product
   tolerance, and sample images.

You can also import any YOLOv5, v8 or v11 detector exported with
`yolo export model=best.pt format=onnx` (**Import ONNX model**). Class names are read from the model.

The command-line tools do the same jobs:
`python tools/train_starter.py` (starter detector), `python tools/train_ocr.py` (plate OCR),
`python tools/generate_samples.py` (test videos and answer key).

---

## Number plate recognition

* Uses the plate camera if one is configured, otherwise the plate region of the counting camera.
* Reads are voted across frames. The plate is accepted after 3 or more agreeing reads with confidence
  of at least 60%.
* Formats are normalised to `LETTERS-DIGITS` (for example `LES-4721`, `BKF-456`, `TLA-552`,
  `ICT-1234`). Letter/digit confusions are fixed by position (`LE5` → `LES`, `47Z1` → `4721`). The
  province is guessed from the series code.
* The clerk corrects a read with one click (✎). The correction is audited.
* An open gate pass whose vehicle number matches the read plate (one OCR error allowed) is offered
  automatically. A gate pass whose plate doesn't match raises a *plate mismatch* alert.
* **Better accuracy on real plates:** the bundled character OCR is trained on rendered plates. For
  production you can plug in a PaddleOCR text-recognition model exported to ONNX under *Settings →
  Number plate OCR*, which needs the `.onnx` file plus its dictionary `.txt`.

---

## Users, roles and security

| Role | Can do |
|---|---|
| Admin | everything, including cameras, models, users, settings and soft-deleting records |
| Supervisor | approve mismatches (PIN), review low-confidence counts, adjust counts with a reason, edit products |
| Clerk | run sessions, enter and import gate passes, view history and reports; cannot delete or change counted records |

* Passwords and PINs use scrypt hashes. Five wrong passwords lock the account for 2 minutes.
* RTSP credentials, SMTP, WhatsApp and SMS secrets, and driver phone numbers are encrypted in the
  database with Fernet (AES + HMAC). The key is protected with Windows DPAPI (machine scope).
* SQLite triggers make `audit_log` append-only, and block deleting `count_events`, `sessions` and
  `evidence_files` or changing evidence hashes.

---

## Licensing and the key generator

One-time setup on the **vendor's** PC:

```bat
python tools\keygen.py init
```

This creates `tools\vendor_keys\vendor_private.pem`. **Keep it secret and back it up.** It is
git-ignored. The command also installs the matching public key into
`nomload\licensing\vendor_public_key.pem`, which is shipped inside the app. A build without the public
key can only run in trial mode.

```bat
:: 50 Professional keys (4 bays), perpetual
python tools\keygen.py batch --tier professional --count 50 --out pro_keys.csv
:: Starter keys that expire
python tools\keygen.py batch --tier starter --count 10 --expiry 2027-06-30 --out starter.csv
:: Machine-locked activation key from the customer's "PC request code" (Settings → Licence)
python tools\keygen.py activation --request-code ABCDE-FGHIJ-KLMNO-PQ --tier enterprise
:: Revoke leaked keys -> send revoked.nlr to customers (Settings → Import revocation list)
python tools\keygen.py revoke --ids 1001 1002 --out revoked.nlr
python tools\keygen.py verify NLC-XXXXXX-...
python tools\keygen.py gui          :: simple window for the sales team
```

| Tier | Bays |
|---|---|
| Starter | 1 |
| Professional | 4 |
| Enterprise | unlimited |
| Trial | 2 bays for 14 days, reports watermarked "TRIAL" |

A product key binds itself to the first PC it is activated on. Copying the installation to another PC
invalidates it. For a PC replacement, issue a machine-locked activation key from the new PC's request
code. `build\build_keygen.bat` builds a standalone `NomLoadKeygen.exe` for the vendor; never ship it to
customers.

---

## Building the Windows installer

Requirements: Windows 10/11 x64, Python 3.11 x64, and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

Double-click **`build\build_windows.bat`** (or run it from a Command Prompt). The window stays open
at the end and on any error, so you can read what happened. If no licensing key pair exists yet it
creates one for you (`tools\keygen.py init`) and reminds you to back up the private key.

The script:

1. creates `.venv-build` and installs `requirements-dev.txt`
2. runs the pytest suite
3. renders the icons
4. runs PyInstaller (`build\nomload.spec`, one-folder build)
5. **self-tests the packaged exe** (`dist\NomLoad\NomLoad.exe --selftest`); the installer is only built if
   every check passes
6. compiles `build\installer.iss` → `dist\installer\NomLoadCounter_Setup_1.0.0.exe`
   (if Inno Setup is not installed you still get the ready-to-run program in `dist\NomLoad\NomLoad.exe`)

**Build troubleshooting**

| Message | Fix |
|---|---|
| `Python was not found` | Install Python 3.11 64-bit and tick *Add python.exe to PATH*, then open a new window. |
| `Package installation failed` | The first build downloads packages, so the PC needs internet once. Re-run. |
| `Tests failed` | Read the failing test name above the message; run `.venv-build\Scripts\python -m pytest -q tests` to see details. |
| `Self-test failed` | `dist\selftest_report.txt` lists the failing check. |
| Inno Setup warning | Install Inno Setup 6 and run the script again. |

The self-test runs in a throw-away data folder and covers the database and integrity triggers,
login/PIN, licensing, model loading, plate OCR on the sample plate video, a **full loading session
through the real bay runtime** on `flour_mill_bay.mp4` (count within 5% of the answer key), all PDF
reports, Excel export, evidence hashing and the evidence pack. You can run it at a customer site at any
time:

```bat
"C:\Program Files\Devnom\NomLoad Counter\NomLoad.exe" --selftest --report selftest.txt
```

The installer puts the program in `Program Files\Devnom\NomLoad Counter` and creates
`%PROGRAMDATA%\Devnom\NomLoad`, writable by all users. That folder is kept on uninstall. The installer
can optionally add auto-start at Windows login.

GPU: `pip uninstall onnxruntime && pip install -r requirements-gpu.txt` before building (DirectML works
on NVIDIA, AMD and Intel GPUs), then tick *Settings → Use GPU*.

---

## Testing and accuracy

```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # full suite (counting, crossing, direction, tracker, sessions,
                                         # matching, licensing, database, plates, tamper, alerts, reports, e2e)
python tools/evaluate.py                 # counting accuracy per sample video → samples/accuracy_report.csv
python -m nomload --selftest             # end-to-end self test
```

The sample videos in `samples/` are synthetic loading scenes made by
`nomload/training/synth.py`. They include bags on the head, shoulder and back, cartons stacked in arms,
hand trolleys with 4–6 items, a belt conveyor, several labourers crossing at once, labourers pausing on
the line, and items carried back out of the truck. `answer_key.csv` holds the true IN, OUT and net counts
per product.

Accuracy of the bundled starter model on the sample videos (`python tools/evaluate.py`, all frames
analysed):

| Sample video | Scene | True net count | Counted | Accuracy |
|---|---|---|---|---|
| flour_mill_bay.mp4 | bags on head / shoulder / back, pauses on the line, one bag carried back | 25 | 24 | 96.0 % |
| fmcg_cartons_bay.mp4 | stacked cartons in arms, trolleys with 4-6 shrink packs | 72 | 70 | 97.2 % |
| beverage_conveyor_bay.mp4 | belt conveyor + crates/cartons in arms and on trolleys | 90 | 80 | 88.9 % |
| mixed_busy_bay.mp4 | crowded: several labourers crossing together, mixed products | 52 | 52 | 92.3 % |

Overall: 239 items, 17 counting errors (92.9 %). About 3 % of counts were flagged for supervisor review (mostly items that appeared from behind a
labourer right on the line). Processing ran at 150-180 frames/s per video on a 4-core CPU
(about 4 ms per inference), far above the 15-25 fps a camera delivers.
The weakest case is cartons tightly stacked on trolleys; site training improves it most.

These numbers measure the whole pipeline (detector + tracker + counter) on synthetic footage. Real-site
accuracy depends on camera placement and on training with the site's own frames. Always validate on
recorded customer footage with a hand-counted answer key in the same CSV format before go-live (copy
the video and an `answer_key.csv` into a folder and run `tools/evaluate.py --folder <folder>`).

---

## Performance tuning

The window never waits for slow work: cameras, AI and recording run in one thread per bay, and camera
tests, calibration frames, reports, evidence packs, model loading and training run in background
threads with a small "working..." indicator. The layout adapts to the screen: the sidebar collapses to
icons below 1440 px width (click « / » to toggle), several bays are shown side by side and every page
scrolls instead of being cut off on 1366×768 gate PCs.


*Settings → Performance*:

* **Skip frames between analyses**: 1 analyses every 2nd frame, which suits 25 fps cameras. Use 2–3 on
  slow PCs.
* **Max processing width**: frames are downscaled before analysis (960 px default; 640 px is enough
  for most bays).
* Use the camera **sub-stream** (e.g. 640×360 or 704×576) for counting. That is the single biggest saving.
* The built-in detector needs about 5–15 ms per frame on a Core i5. Two bays at 12–15 analysed fps
  fit easily on a CPU-only PC. Each bay runs in its own thread, so the UI never blocks.
* **Use GPU** (DirectML) for many bays or large YOLO models.

---

## Branding and translation

* Colours and fonts live in **`nomload/theme/theme.json`** (brand, light and dark palettes). Every
  screen, chart and report reads them. Users switch light/dark with *Appearance*.
* The logo is `nomload/assets/logo.svg` (viewfinder brackets around a counted carton stack, in the
  Devnom family style). After editing it, run `python tools/make_assets.py` to regenerate the PNG and
  ICO files.
* The customer logo is set in *Settings → Company* and printed on every report.
* All UI text goes through `nomload.i18n._()`. To add Urdu, fill `TRANSLATIONS["ur"]` or drop a
  `nomload/translations/ur.json`; selecting Urdu switches the layout to right-to-left.

---

## Known limitations

* The **starter detector and plate OCR are trained only on synthetic data**. They demonstrate the full
  workflow and count the bundled sample videos accurately, but they will not reliably detect real
  bags, cartons or plates until fine-tuned on site footage with the Training wizard. Budget 1–2 hours
  of annotation per site.
* Items that are completely hidden while crossing the line (for example inside a closed trolley or
  under a tarpaulin) cannot be counted visually. Use the *units per detection* rule, or count them as
  a manual adjustment.
* WhatsApp alerts need a Meta WhatsApp Business Cloud API account. SMS needs any HTTP gateway (most
  Pakistani SMS providers offer one).
* The hardware fingerprint changes if the Windows system drive is re-formatted or the motherboard is
  replaced. Issue a new activation key from the request code.

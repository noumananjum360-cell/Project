"""Build the NomLoad Counter user manual (PDF) from real application screenshots.

    python tools/manual/seed_demo.py      # demo database with real loading sessions
    python tools/manual/screenshots.py    # drives the real app and saves screenshots
    python tools/manual/build_manual.py   # writes docs/NomLoad_Counter_User_Manual.pdf
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
WORK = Path(os.environ.get("NOMLOAD_MANUAL_WORK", ROOT / "build" / "manual_work"))
IMG = WORK / "img"
OUT = ROOT / "docs" / "NomLoad_Counter_User_Manual.pdf"

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,  # noqa: E402
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

from nomload import __version__  # noqa: E402

NAVY = colors.HexColor("#1B2A4E")
AMBER = colors.HexColor("#E8A33D")
GREY = colors.HexColor("#5A6475")
LIGHT = colors.HexColor("#F2F4F7")
GREEN = colors.HexColor("#1F9D55")
RED = colors.HexColor("#D64545")
ASSETS = ROOT / "nomload" / "assets"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=20, textColor=NAVY,
                    spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, textColor=NAVY,
                    spaceBefore=12, spaceAfter=6)
BODY = ParagraphStyle("Body", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14.5, spaceAfter=6)
STEP = ParagraphStyle("Step", parent=BODY, leftIndent=16, bulletIndent=2, spaceAfter=3)
CAP = ParagraphStyle("Cap", parent=BODY, fontSize=8.5, textColor=GREY, alignment=TA_CENTER, spaceBefore=3,
                     spaceAfter=12)
NOTE = ParagraphStyle("Note", parent=BODY, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#3A2A08"))
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=9, leading=12, spaceAfter=0)
TOC1 = ParagraphStyle("TOC1", fontName="Helvetica", fontSize=11, leading=20, leftIndent=6)
TOC2 = ParagraphStyle("TOC2", fontName="Helvetica", fontSize=9.5, leading=15, leftIndent=24, textColor=GREY)

_fig = [0]
_sec = [0, 0]


class Doc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm,
                         bottomMargin=18 * mm, title="NomLoad Counter - User Manual", author="Devnom")
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate("cover", [fr], onPage=self._cover),
                               PageTemplate("body", [fr], onPage=self._page)])

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("H1", "H2"):
            level = 0 if f.style.name == "H1" else 1
            key = f"h{id(f)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(f.getPlainText(), key, level=level)
            self.notify("TOCEntry", (level, f.getPlainText(), self.page, key))

    def _cover(self, c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        # carton pattern
        c.setFillColor(colors.HexColor("#22335D"))
        for row in range(0, 30):
            off = (row % 2) * 35
            for col in range(-1, 9):
                c.roundRect(col * 70 + off + 3, row * 34 + 3, 64, 28, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.roundRect(30 * mm, 70 * mm, w - 60 * mm, 150 * mm, 10, fill=1, stroke=0)
        c.drawImage(str(ASSETS / "logo.png"), w / 2 - 22 * mm, 172 * mm, 44 * mm, 44 * mm, mask="auto")
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(w / 2, 155 * mm, "NomLoad")
        c.setFillColor(GREY)
        c.setFont("Helvetica", 13)
        c.drawCentredString(w / 2, 145 * mm, "C O U N T E R")
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w / 2, 120 * mm, "User Manual")
        c.setFont("Helvetica", 11)
        c.setFillColor(GREY)
        c.drawCentredString(w / 2, 110 * mm, "Truck loading counter for bags and cartons")
        c.drawCentredString(w / 2, 103 * mm, f"Version {__version__}")
        c.setFillColor(AMBER)
        c.rect(w / 2 - 20 * mm, 95 * mm, 40 * mm, 1.2 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 10)
        c.drawCentredString(w / 2, 30 * mm, "Devnom")
        c.restoreState()

    def _page(self, c, doc):
        w, h = A4
        c.saveState()
        c.drawImage(str(ASSETS / "logo_128.png"), 18 * mm, h - 15 * mm, 8 * mm, 8 * mm, mask="auto")
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(NAVY)
        c.drawString(28 * mm, h - 11.5 * mm, "NomLoad Counter")
        c.setFont("Helvetica", 9)
        c.setFillColor(GREY)
        c.drawRightString(w - 18 * mm, h - 11.5 * mm, "User Manual")
        c.setStrokeColor(AMBER)
        c.setLineWidth(1.2)
        c.line(18 * mm, h - 16.5 * mm, w - 18 * mm, h - 16.5 * mm)
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, 10 * mm, f"NomLoad Counter {__version__}  ·  Devnom")
        c.drawRightString(w - 18 * mm, 10 * mm, f"Page {doc.page}")
        c.restoreState()


def h1(text):
    _sec[0] += 1
    _sec[1] = 0
    return Paragraph(f"{_sec[0]}. {text}", H1)


def h2(text):
    _sec[1] += 1
    return Paragraph(f"{_sec[0]}.{_sec[1]} {text}", H2)


def p(text):
    return Paragraph(text, BODY)


def steps(*items):
    return [Paragraph(t, STEP, bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def bullets(*items):
    return [Paragraph(t, STEP, bulletText="•") for t in items]


def note(text, kind="note"):
    bg = {"note": colors.HexColor("#FBEFD9"), "ok": colors.HexColor("#E3F4EA"), "bad": colors.HexColor("#FBE6E6")}[kind]
    t = Table([[Paragraph(text, NOTE)]], colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return KeepTogether([t, Spacer(1, 8)])


def fig(name, caption, width_mm=174, crop=None):
    path = IMG / f"{name}.png"
    if not path.exists():
        return Spacer(1, 1)
    if crop:
        from PIL import Image as PImage  # optional, only used for crops
        im = PImage.open(path)
        x0, y0, x1, y1 = crop
        im = im.crop((x0, y0, x1 if x1 > 0 else im.width, y1 if y1 > 0 else im.height))
        path = IMG / f"{name}_crop.png"
        im.save(path)
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(path)).getSize()
    w = width_mm * mm
    h = w * ih / iw
    max_h = 205 * mm
    if h > max_h:
        w, h = w * max_h / h, max_h
    _fig[0] += 1
    img = Image(str(path), width=w, height=h)
    frame = Table([[img]], colWidths=[w + 2])
    frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9CED8")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return KeepTogether([frame, Paragraph(f"Figure {_fig[0]}: {caption}", CAP)])


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), CELL) for c in r] for r in rows]
    if header:
        data[0] = [Paragraph(f"<font color='white'><b>{c}</b></font>", CELL) for c in rows[0]]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E3E6EC")),
          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(st))
    return KeepTogether([t, Spacer(1, 8)])


def pdf_page_png(pdf: Path, name: str):
    """Render page 1 of a generated report so the manual shows the real output."""
    out = IMG / name
    if pdf.exists():
        subprocess.run(["pdftoppm", "-png", "-r", "70", "-f", "1", "-l", "1", "-singlefile", str(pdf), str(out)],
                       check=False)
    return out.with_suffix(".png").exists()


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf_page_png(WORK / "pdf" / "certificate.pdf", "40_certificate_pdf")
    pdf_page_png(WORK / "pdf" / "daily.pdf", "41_daily_pdf")
    toc = TableOfContents()
    toc.levelStyles = [TOC1, TOC2]
    S = [NextPageTemplate("body"), PageBreak(), Paragraph("Contents", ParagraphStyle("TOCH", parent=H1)), toc,
         PageBreak()]

    # 1 ---------------------------------------------------------------- introduction
    S += [h1("Introduction"),
          p("NomLoad Counter counts bags and cartons as they are loaded onto a truck, using the CCTV cameras "
            "already installed at the loading bay. It reads the truck's number plate and compares the counted "
            "quantity with the gate pass or invoice. If the quantity does not match, the truck is held and an "
            "alarm sounds until a supervisor releases it with a PIN and a written reason."),
          p("Every loading is recorded with a video clip, a photo of each counted item and the plate image. These "
            "files are protected with a digital fingerprint (SHA-256) so any later change can be detected."),
          h2("How it works"),
          *steps("The clerk selects the gate pass for the truck on the <b>Live Bays</b> screen.",
                 "The camera watches the truck entrance. Each bag or carton that crosses the counting line "
                 "<b>into</b> the truck adds 1; an item carried back <b>out</b> subtracts 1.",
                 "The number plate is read automatically and matched with the gate pass.",
                 "The clerk presses <b>Close &amp; verify</b>. The result is <font color='#1F9D55'><b>CLEARED</b>"
                 "</font> or <font color='#D64545'><b>MISMATCH</b></font>.",
                 "Every truck can be searched later, and a certificate or evidence pack can be printed."),
          h2("User roles"),
          table([["Role", "What the user can do"],
                 ["Clerk", "Run loading sessions, enter and import gate passes, correct plates, view history and "
                           "reports. Cannot delete or change counted records."],
                 ["Supervisor", "Everything a clerk can do, plus: release mismatched trucks with PIN, review "
                                "doubtful counts, adjust counts with a reason, edit products."],
                 ["Admin", "Everything, including cameras, AI models, users, settings and licence."]], [32, 142]),
          PageBreak()]

    # 2 ---------------------------------------------------------------- installation
    S += [h1("Installation and first start"),
          h2("Computer requirements"),
          table([["Item", "Minimum", "Recommended"],
                 ["Windows", "Windows 10 64-bit", "Windows 10/11 64-bit"],
                 ["Processor", "Intel Core i5 (6th gen) or equal", "Core i5/i7 10th gen or newer"],
                 ["Memory", "8 GB", "16 GB"],
                 ["Disk", "20 GB free", "500 GB+ for long evidence history"],
                 ["Network", "Same network as the cameras / NVR", "Wired Gigabit"],
                 ["Bays per PC (CPU only)", "2", "4 or more with a GPU"]], [44, 65, 65]),
          h2("Installing"),
          *steps("Run <b>NomLoadCounter_Setup_1.0.0.exe</b> and follow the setup wizard.",
                 "Tick <i>Create a desktop shortcut</i>. On the gate PC also tick <i>Start NomLoad when Windows "
                 "starts</i>.",
                 "Start NomLoad from the desktop icon. The start screen appears while the AI models load."),
          fig("01_splash", "Start screen", 110),
          h2("Logging in"),
          p("Enter your username and password and press <b>Log in</b>. After installation the first account is "
            "<b>admin</b> with password <b>admin123</b> and supervisor PIN <b>1234</b>. You will be asked to choose a "
            "new password straight away."),
          fig("02_login", "Login screen"),
          note("Five wrong passwords lock the account for two minutes. An Admin can reset a forgotten password "
               "under <b>Users</b>."),
          h2("Activating the licence"),
          *steps("Log in as Admin and open <b>Settings</b>. Scroll to <b>Licence</b>.",
                 "Paste the licence key (it starts with <b>NLC-</b>) and press <b>Activate</b>.",
                 "The status bar at the bottom-left changes to <i>Professional: Licensed</i> (or your tier)."),
          p("Without a key NomLoad runs as a 14-day trial with 2 bays, and reports carry a TRIAL watermark. A key "
            "locks to the first PC it is activated on. If the PC is replaced, send the <b>PC request code</b> shown "
            "in the same section to Devnom for a new activation key."),
          PageBreak()]

    # 3 ---------------------------------------------------------------- screen tour
    S += [h1("Main screen"),
          p("The menu on the left opens each part of the program. Users only see the pages their role allows. "
            "At the bottom-left are the user's name and role and links for <b>Appearance</b> (light / dark), "
            "<b>Change password</b> and <b>Log out</b>."),
          fig("03_dashboard", "Dashboard with the menu on the left"),
          table([["Menu", "Use it to"],
                 ["Dashboard", "See today's trucks, units dispatched, mismatches, loading times and busiest hours."],
                 ["Live Bays", "Watch the cameras and run loading sessions."],
                 ["Sessions", "Manage gate passes, today's trucks and the review queue."],
                 ["History", "Search past trucks, view evidence, print certificates."],
                 ["Reports", "Daily dispatch, mismatch report, Excel export, audit log."],
                 ["Products", "Product list, units per stack and tolerance."],
                 ["Cameras", "Bays, cameras and calibration (Admin)."],
                 ["Training", "Teach the AI your own bags and cartons (Admin)."],
                 ["Users", "User accounts and roles (Admin)."],
                 ["Settings", "Company details, alerts, performance and licence (Admin)."]], [32, 142]),
          p("The <b>status bar</b> at the bottom shows the licence, the AI model in use, messages waiting to be "
            "sent and the alert bell. Click the bell to see all alerts."),
          note("On smaller screens (for example 1366 × 768) the menu shrinks to icons. Click <b>»</b> at the bottom "
               "of the menu to open it again."),
          PageBreak()]

    # 4 ---------------------------------------------------------------- bays & cameras
    S += [h1("Setting up bays and cameras"),
          p("A <b>bay</b> is one truck loading point. Each bay needs one <b>counting camera</b> looking at the truck "
            "entrance. A <b>plate camera</b> is optional; without it the plate is read from the counting camera."),
          fig("22_cameras", "Cameras page: bays on the left, cameras of the selected bay on the right"),
          h2("Adding a bay"),
          *steps("Open <b>Cameras</b> and press <b>Add bay</b>.",
                 "Enter a name such as <i>Bay 1 - Flour</i>.",
                 "Tick <i>Start a session automatically when a truck is detected</i> if trucks should be counted even "
                 "before the clerk selects a gate pass."),
          h2("Adding an IP camera (Hikvision, Dahua and others)"),
          *steps("Select the bay and press <b>Add camera</b>.",
                 "Choose the role: <b>Counting camera</b> or <b>Number plate camera</b>.",
                 "Source: <b>IP camera / NVR (RTSP)</b>. Select the brand and enter the IP address, username, "
                 "password and channel. The RTSP address is filled in automatically.",
                 "Tick <b>Use sub-stream</b> on ordinary PCs. It is enough for counting and uses far less "
                 "processing power.",
                 "Press <b>Test connection</b>. A picture from the camera must appear.",
                 "Press <b>Save</b>."),
          fig("23_add_camera_rtsp", "Add camera with the RTSP helper and a successful connection test", 120),
          table([["Brand", "Address format"],
                 ["Hikvision / HiLook", "rtsp://user:pass@IP:554/Streaming/Channels/101 (102 = sub-stream)"],
                 ["Dahua / CP Plus", "rtsp://user:pass@IP:554/cam/realmonitor?channel=1&amp;subtype=0 (1 = sub-stream)"],
                 ["Uniview", "rtsp://user:pass@IP:554/unicast/c1/s0/live"],
                 ["USB webcam", "Source: USB webcam, device 0"],
                 ["Recorded video", "Source: Video file (for testing and training)"]], [40, 134]),
          h2("Calibrating the counting line"),
          p("Calibration tells NomLoad where the truck entrance is. Do it once per camera, and again if the camera "
            "is moved."),
          *steps("Select the camera and press <b>Calibrate</b>. A live picture opens.",
                 "Choose <b>Counting line</b> and drag a line across the truck entrance, from one side of the "
                 "tailgate to the other.",
                 "Check the amber arrow. It must point <b>into the truck</b>. If not, press <b>Flip direction</b>.",
                 "Optional: draw <b>Ignore zones</b> over areas that must never be counted, such as the stock pile or "
                 "a walkway. Click the corners and double-click to finish.",
                 "For the plate, choose <b>Plate region</b> and drag a box where the number plate appears.",
                 "Keep <b>Save this view as the tamper-detection reference</b> ticked and press <b>Save calibration"
                 "</b>.",
                 "Press <b>Apply &amp; restart bays</b> on the Cameras page."),
          fig("24_calibration", "Calibration: counting line with direction arrow and tolerance band"),
          note("The shaded band around the line prevents double counting when a labourer stops or sways on the line. "
               "Widen it with <b>Line tolerance band</b> if workers often stand on the line."),
          PageBreak()]

    # 5 ---------------------------------------------------------------- products
    S += [h1("Products"),
          p("Every item on a gate pass must exist as a product. The product tells NomLoad what the camera should "
            "look for and how many units each detected item is worth."),
          fig("21_products", "Products page"),
          table([["Field", "Meaning"],
                 ["Name / SKU", "As written on your gate passes and invoices."],
                 ["Detector class", "What the camera recognises: bag, carton, crate, pack, or a custom class trained "
                                    "for your site."],
                 ["Units per detection", "Units counted for each detected item. Example: a shrink pack of 12 bottles "
                                         "counted as 12 units, or 1 if the gate pass counts packs."],
                 ["Tolerance", "Allowed difference for this product. Empty = the general tolerance from Settings."],
                 ["Sample images", "Photos of the product for reference and training."]], [40, 134]),
          note("If one gate pass has two products of the same class (for example flour bags and sugar bags), the "
               "clerk selects the product being loaded on the Live Bays screen. Counts go to the selected product."),
          PageBreak()]

    # 6 ---------------------------------------------------------------- gate passes
    S += [h1("Gate passes"),
          fig("12_sessions_gate_passes", "Sessions → Gate passes"),
          h2("Entering a gate pass"),
          *steps("Open <b>Sessions</b> and press <b>New gate pass</b>.",
                 "Enter the gate pass or invoice number, vehicle number, customer, driver and destination.",
                 "Select each product and type the quantity. Use <b>Add product</b> for more lines.",
                 "Press <b>Save</b>."),
          fig("14_new_gate_pass", "New gate pass with two products", 120),
          h2("Importing from Excel or CSV"),
          p("Press <b>Template</b> to save an example file, fill it in Excel, then press <b>Import CSV / Excel</b>. "
            "One row per product; rows with the same gate pass number become one gate pass."),
          table([["gate_pass", "vehicle", "customer", "product", "quantity"],
                 ["GP-1001", "LES-4721", "Al-Madina Traders", "Flour 50kg bag", "400"],
                 ["GP-1001", "LES-4721", "Al-Madina Traders", "Sugar 50kg bag", "100"],
                 ["GP-1002", "TLA-552", "City Distributors", "Carton 1.5L x6", "600"]], [26, 26, 46, 46, 30]),
          p("Optional columns: driver, phone, destination. Product names must match the Products page."),
          PageBreak()]

    # 7 ---------------------------------------------------------------- loading
    S += [h1("Loading a truck"),
          fig("04_live_bays", "Live Bays with two bays loading"),
          h2("Starting"),
          *steps("Open <b>Live Bays</b>. Check that the camera shows <i>Camera online</i>.",
                 "When the truck is in position press <b>Start loading</b>.",
                 "Select the truck's gate pass (search by number, vehicle or customer) and press <b>Start loading</b>. "
                 "If the gate pass is not in the list, press <b>New gate pass</b>."),
          fig("06_gate_pass_picker", "Selecting the gate pass", 150),
          h2("During loading"),
          p("Each counted item gets a box and a number on the video, and a green <b>+1</b> appears when it crosses "
            "into the truck. The large number shows the total counted against the gate pass quantity."),
          fig("05_live_single_bay", "One bay enlarged (double-click the video). Counter, plate, gate pass and "
                                    "per-product counts"),
          table([["On screen", "Meaning"],
                 ["Big number / expected", "Units counted so far / quantity on the gate pass."],
                 ["Progress bar", "Blue while loading, green when complete, red if more than the gate pass."],
                 ["Plate box", "Number plate read by the camera with its confidence."],
                 ["⚠ count(s) need review", "Items the camera was not sure about. A supervisor checks them."],
                 ["Product buttons", "Select the product being loaded when two products look alike."],
                 ["Camera online / Truck in bay", "Camera and truck status."]], [48, 126]),
          h2("Correcting the number plate"),
          p("If the plate is wrong or empty, press the pencil button next to the plate, type the correct number and "
            "press <b>Save plate</b>. The correction is recorded in the audit log."),
          fig("07_plate_correct", "Correcting the plate", 95),
          h2("Reviewing doubtful counts"),
          p("When an item was partly hidden, the count is marked for review instead of being added silently. Press "
            "<b>Review</b>, enter the supervisor PIN, look at each photo and press <b>Accept</b> or <b>Reject</b>."),
          fig("11_review_counts", "Supervisor review of doubtful counts with photos", 150),
          h2("Finishing: Close & verify"),
          *steps("When loading is complete press <b>Close &amp; verify</b>.",
                 "NomLoad compares every product with the gate pass, using the allowed tolerance."),
          fig("09_result_cleared", "CLEARED: the truck may leave", 140),
          fig("10_result_mismatch", "MISMATCH: the alarm sounds and the truck stays on hold", 140),
          h2("Releasing a mismatched truck"),
          p("Only a supervisor can release a truck with a mismatch. Press <b>Supervisor release</b>, select the "
            "supervisor, enter the PIN and write the reason, for example <i>5 bags short, customer informed</i>."),
          fig("08_supervisor_approval", "Supervisor approval with PIN and reason", 110),
          note("If the truck leaves the bay while a session is open, NomLoad closes and checks the loading "
               "automatically (this can be turned off in Settings)."),
          PageBreak()]

    # 8 ---------------------------------------------------------------- history
    S += [h1("History and evidence"),
          p("Open <b>History</b> to find any truck. Search by date, plate, gate pass number, product, bay or status, "
            "then double-click a row."),
          fig("15_history", "History search"),
          fig("16_session_summary", "Session details: quantities, plate and who did what"),
          fig("17_session_snapshots", "Photo of every counted item (double-click to enlarge)"),
          h2("Checking and sharing evidence"),
          bullets("<b>Play clip</b> opens the video of the whole loading.",
                  "<b>Verify evidence</b> checks every file against its stored fingerprint. Any edited or missing "
                  "file is shown in red.",
                  "<b>Evidence pack</b> saves a ZIP file with the video, photos, plate image and a PDF summary to send "
                  "to a distributor in a dispute.",
                  "<b>Loading certificate</b> prints the PDF certificate for this truck.",
                  "The <b>Audit trail</b> tab lists every action on this truck with user and time."),
          fig("18_session_evidence", "Evidence check: all files intact"),
          fig("19_session_audit", "Audit trail of one truck"),
          PageBreak()]

    # 9 ---------------------------------------------------------------- reports
    S += [h1("Reports"),
          fig("20_reports", "Reports page"),
          table([["Report", "Contents"],
                 ["Truck loading certificate", "One truck: quantities, plate, photos, evidence fingerprints and "
                                               "signature lines."],
                 ["Daily dispatch summary", "All trucks of one day, units per product and mismatches."],
                 ["Mismatch report", "Every truck with a difference and the supervisor's release reason."],
                 ["Excel export", "Sessions, products, every count event and alerts for a date range."],
                 ["Audit log", "Every action by every user. Records cannot be edited or deleted."]], [50, 124]),
          fig("40_certificate_pdf", "Example loading certificate (PDF)", 120),
          fig("41_daily_pdf", "Example daily dispatch summary (PDF)", 120),
          p("Your company name, address and logo are printed on every report. Set them in <b>Settings → Company</b>."),
          PageBreak()]

    # 10 --------------------------------------------------------------- training
    S += [h1("Training NomLoad for your products"),
          p("Every factory's bags and cartons look different. For the best accuracy, train NomLoad with video from "
            "your own bay before going live. This takes about one to two hours of work."),
          h2("Step 1: Collect frames"),
          *steps("Export 10-30 minutes of normal loading from the NVR as an MP4 file.",
                 "Open <b>Training</b>, press <b>New dataset</b> and give it a name.",
                 "On <b>1 Collect frames</b> press <b>Choose video and extract</b>. NomLoad saves one picture every "
                 "15 frames (300 pictures by default)."),
          fig("25_training_collect", "Collecting frames"),
          h2("Step 2: Annotate"),
          *steps("Open <b>2 Annotate</b>. Press <b>Auto-label</b> so NomLoad draws the boxes it already recognises.",
                 "Correct the boxes: drag to draw a new box, select a box and press 1-9 to change its class, "
                 "Delete to remove it.",
                 "Press <b>Save &amp; next</b> (or PgDn) and continue until all pictures are done."),
          fig("26_training_annotate", "Annotation tool"),
          h2("Step 3: Train"),
          p("On <b>3 Train</b> keep <i>Built-in trainer</i> and <i>Start from current model</i>, and press "
            "<b>Start training</b>. 1500 iterations take about 15 minutes. Counting continues while training runs."),
          fig("27_training_train", "Training progress"),
          h2("Step 4: Activate"),
          p("On <b>4 Evaluate &amp; activate</b>, check precision and recall, then select the new model and press "
            "<b>Activate</b>. All bays switch to it immediately. The previous model stays in the list, so you can "
            "switch back."),
          fig("28_training_models", "Models list"),
          PageBreak()]

    # 11 --------------------------------------------------------------- users / settings
    S += [h1("Users"),
          fig("29_users", "Users page"),
          *steps("Press <b>New user</b>, enter username, full name and role.",
                 "Give a temporary password; the user must change it at first login.",
                 "Supervisors and Admins also need a <b>PIN</b> (4 or more digits) for approvals.",
                 "To stop someone using NomLoad, select the user and press <b>Enable / disable</b>. Users are never "
                 "deleted, so the audit log stays complete."),
          fig("30_edit_user", "Editing a user", 95),
          PageBreak(),
          h1("Settings"),
          fig("32_settings_top", "Settings"),
          table([["Section", "Main settings"],
                 ["Company", "Name, address and logo printed on reports; language."],
                 ["Counting & matching", "Allowed difference in units and %; confidence below which counts go to "
                                         "review."],
                 ["Performance", "Frames skipped between analyses, processing width, GPU. Raise <i>Skip frames</i> "
                                 "only if the PC is too slow."],
                 ["Sessions & evidence", "Video kept before a session, clip frame rate, automatic start and close."],
                 ["Cameras", "Offline alert time; tamper detection (covered, blurred or moved camera)."],
                 ["Alerts on this PC", "Alarm sound and volume."],
                 ["Remote alerts", "Email, WhatsApp and SMS to the owner. Choose which events are sent. Messages are "
                                   "kept and sent when internet is available."],
                 ["Licence", "Status, PC request code, activate key, import revocation list."],
                 ["Data", "Data folder and database backup."]], [42, 132]),
          note("Press <b>Save settings</b> at the top after making changes."),
          h2("Alerts"),
          p("Alerts appear as a coloured bar at the top of the screen and in the bell list at the bottom-right."),
          fig("33_alerts", "Alerts list", 150),
          table([["Alert", "When"],
                 ["Quantity mismatch", "A truck was closed with a difference (alarm sounds)."],
                 ["Camera offline", "No video for longer than the set time."],
                 ["Camera tampering", "Camera covered, blurred, moved or pointed elsewhere."],
                 ["Plate does not match", "The plate read differs from the gate pass vehicle number."],
                 ["Low-confidence count", "An item needs supervisor review."]], [50, 124]),
          PageBreak()]

    # 12 --------------------------------------------------------------- appearance + troubleshooting
    S += [h1("Appearance"),
          p("Click <b>Appearance</b> at the bottom of the menu to switch between the light and dark look. Dark is "
            "easier on the eyes in a dim gate cabin."),
          fig("35_dark_live", "Dark appearance"),
          PageBreak(),
          h1("Troubleshooting"),
          table([["Problem", "What to do"],
                 ["Camera offline", "Check the network cable and that the camera/NVR is powered. Open Cameras, select "
                                    "the camera, press Edit → Test connection. Check username, password and channel."],
                 ["Picture appears but nothing is counted", "Check the calibration: the arrow must point into the "
                                                            "truck and the line must cross the path of the labourers."],
                 ["Counts too high", "Widen the line tolerance band; add ignore zones over the stock pile; train with "
                                     "your own video."],
                 ["Counts too low", "Mount the camera higher so items are not hidden behind labourers; use the main "
                                    "stream instead of sub-stream; set Skip frames to 0; train with your own video."],
                 ["Plate not read", "Draw the plate region in the calibration or add a plate camera; correct the plate "
                                    "manually with the pencil button."],
                 ["Program slow", "Use the camera sub-stream, lower Max processing width to 640, or raise Skip "
                                  "frames to 1."],
                 ["Camera tampering alert", "Check the camera is not covered or moved. If it was moved on purpose, "
                                            "calibrate it again."],
                 ["Licence expired / not valid", "Settings → Licence: activate a key. If the PC was replaced, send "
                                                 "the PC request code to Devnom."],
                 ["Forgot password", "Ask an Admin to reset it under Users."]], [52, 122]),
          h2("Getting help"),
          p("The log file is in the data folder (<b>Settings → Data → Open folder</b>, then <i>logs</i>). Send it to "
            "Devnom support together with a description of the problem. To check that the installation is healthy, "
            "run <b>NomLoad.exe --selftest</b> from the installation folder."),
          PageBreak()]

    # 13 --------------------------------------------------------------- quick reference
    S += [h1("Quick reference for the gate clerk"),
          table([["Step", "Action"],
                 ["1", "Truck arrives at the bay → <b>Live Bays</b> → <b>Start loading</b> → select the gate pass."],
                 ["2", "Check the plate. Wrong? Press the pencil and correct it."],
                 ["3", "If loading two similar products, select the product being loaded."],
                 ["4", "Watch the counter. ⚠ review messages: call the supervisor."],
                 ["5", "Loading finished → <b>Close &amp; verify</b>."],
                 ["6", "<font color='#1F9D55'><b>CLEARED</b></font> → truck may leave. Print the certificate if "
                       "needed."],
                 ["7", "<font color='#D64545'><b>MISMATCH</b></font> → truck stays. Call the supervisor for "
                       "release or correction."]], [16, 158]),
          Spacer(1, 10),
          note("Daily checks: cameras show <i>Camera online</i> · camera lenses clean · no open alerts · end of day: "
               "print the <b>Daily dispatch summary</b>.", "ok")]

    flat = []
    for x in S:
        flat.extend(x if isinstance(x, list) else [x])
    doc = Doc(OUT)
    doc.multiBuild(flat)
    print("wrote", OUT)


if __name__ == "__main__":
    build()

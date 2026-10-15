# PyInstaller spec for NomLoad Counter (one-folder build, packaged by Inno Setup).
#   pyinstaller --noconfirm build/nomload.spec
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
block_cipher = None

datas = [
    (str(ROOT / "nomload" / "assets"), "nomload/assets"),
    (str(ROOT / "nomload" / "theme" / "theme.json"), "nomload/theme"),
    (str(ROOT / "models"), "models"),
    (str(ROOT / "samples"), "samples"),
]
pub = ROOT / "nomload" / "licensing" / "vendor_public_key.pem"
if pub.exists():
    datas.append((str(pub), "nomload/licensing"))
tr = ROOT / "nomload" / "translations"
if tr.exists():
    datas.append((str(tr), "nomload/translations"))

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["onnxruntime", "PySide6.QtSvg", "PySide6.QtMultimedia", "reportlab.graphics.barcode.common",
                   "openpyxl.cell._writer"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "torchvision", "ultralytics", "scipy", "pandas", "IPython",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="NomLoad",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "nomload" / "assets" / "app.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="NomLoad")

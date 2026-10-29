# PyInstaller spec - folder build: dist/NomLoyal/NomLoyal.exe
# Build with build.bat (it runs the tests first).
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
hidden = (["PySide6.QtSvg", "PySide6.QtPrintSupport", "qrcode.image.svg", "qrcode.image.base"]
          + collect_submodules("app")
          # OpenCV needs all of NumPy's compiled parts; some PyInstaller/NumPy combinations miss a few
          + collect_submodules("numpy", filter=lambda name: ".tests" not in name and "f2py" not in name))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[("assets", "assets"), ("templates", "templates")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtPdf", "PySide6.QtWebSockets"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="NomLoyal",
    icon="assets/brand/app.ico",
    console=False,
    disable_windowed_traceback=False,
    version="version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="NomLoyal")

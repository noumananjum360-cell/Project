# Vendor-only licence key generator (never ship to customers).
#   pyinstaller --noconfirm build/keygen.spec
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
a = Analysis([str(ROOT / "tools" / "keygen.py")], pathex=[str(ROOT)], datas=[],
             hiddenimports=["PySide6.QtWidgets"], excludes=["tkinter", "matplotlib", "cv2", "onnxruntime", "numpy"])
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name="NomLoadKeygen", console=True,
          icon=str(ROOT / "nomload" / "assets" / "app.ico"))

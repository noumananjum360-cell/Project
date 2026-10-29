"""Small helpers to render text with real fonts through Qt (works headless)."""
from __future__ import annotations

import os

import numpy as np

_app = None


_fonts_loaded = False


def _load_system_fonts():
    """Qt's offscreen/minimal platforms only look in PySide6/lib/fonts, which pip wheels leave
    empty on Windows. Register the fonts installed on the PC so plates render with real text."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    from pathlib import Path

    from PySide6.QtGui import QFontDatabase
    dirs = []
    if os.name == "nt":
        dirs.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    else:
        dirs += [Path("/usr/share/fonts"), Path.home() / ".fonts"]
    wanted = ("arial", "calibri", "segoeui", "tahoma", "verdana", "dejavusans", "liberationsans", "freesans")
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*.ttf"):
            if f.stem.lower().replace("-", "").startswith(wanted):
                QFontDatabase.addApplicationFont(str(f))


def ensure_qt():
    global _app
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        # Windows can render off-screen with its native platform (system fonts available);
        # elsewhere (servers/CI) use the offscreen platform.
        if os.name != "nt":
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _app = QGuiApplication([])
    from PySide6.QtGui import QFontDatabase
    if os.environ.get("QT_QPA_PLATFORM") in ("offscreen", "minimal") or not QFontDatabase.families():
        _load_system_fonts()
    return QGuiApplication.instance()


FONT_FAMILIES = ["Arial", "Liberation Sans", "DejaVu Sans", "FreeSans", "Inter", "Carlito", "Segoe UI",
                 "Verdana", "Tahoma"]


def available_fonts() -> list[str]:
    ensure_qt()
    from PySide6.QtGui import QFontDatabase
    have = set(QFontDatabase.families())
    if not have:
        raise RuntimeError("No fonts available to Qt - cannot render plates")
    fams = [f for f in FONT_FAMILIES if f in have]
    return fams or [sorted(have)[0]]


def qimage_to_bgr(img) -> np.ndarray:
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * h).reshape(h, bpl)
    arr = arr[:, : w * 3].reshape(h, w, 3)
    return arr[:, :, ::-1].copy()


def render_plate(text: str, province: str = "Punjab", style: str = "white", font: str | None = None,
                 width: int = 260, height: int = 84, bold: bool = True) -> np.ndarray:
    """Render a Pakistani style number plate as a BGR image."""
    ensure_qt()
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    from nomload.core.plate_formats import PROVINCE_HEADERS

    font = font or available_fonts()[0]
    img = QImage(width, height, QImage.Format.Format_RGB888)
    bg = {"white": QColor(245, 245, 240), "yellow": QColor(250, 205, 40), "green": QColor(240, 245, 238)}[style]
    img.fill(QColor(60, 60, 60))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setBrush(bg)
    p.setPen(QPen(QColor(20, 20, 20), 3))
    p.drawRoundedRect(QRectF(2, 2, width - 4, height - 4), 8, 8)
    if style == "green":
        p.fillRect(QRectF(5, 5, width - 10, height * 0.18), QColor(0, 110, 60))
    header = PROVINCE_HEADERS.get(province, "")
    if header:
        hf = QFont(font)
        hf.setPixelSize(int(height * 0.15))
        hf.setBold(True)
        p.setFont(hf)
        p.setPen(QColor(255, 255, 255) if style == "green" else QColor(30, 30, 30))
        p.drawText(QRectF(0, 3, width, height * 0.22), Qt.AlignmentFlag.AlignCenter, header)
    mf = QFont(font)
    mf.setPixelSize(int(height * 0.56))
    mf.setBold(bold)
    p.setFont(mf)
    p.setPen(QColor(10, 10, 10))
    p.drawText(QRectF(0, height * 0.22, width, height * 0.74), Qt.AlignmentFlag.AlignCenter, text.replace("-", " - " if len(text) < 7 else "-"))
    p.end()
    return qimage_to_bgr(img)


def render_glyph(ch: str, font: str, size: int = 48, bold: bool = True) -> np.ndarray:
    """Render a single dark glyph on white (grayscale uint8), tightly cropped."""
    ensure_qt()
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    img = QImage(size * 2, size * 2, QImage.Format.Format_RGB888)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(font)
    f.setPixelSize(size)
    f.setBold(bold)
    p.setFont(f)
    p.setPen(QColor(0, 0, 0))
    p.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, ch)
    p.end()
    g = qimage_to_bgr(img)[:, :, 0]
    ys, xs = np.where(g < 128)
    if len(xs) == 0:
        return g
    return g[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

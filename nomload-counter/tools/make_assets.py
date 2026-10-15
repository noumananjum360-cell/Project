"""Render PNG/ICO assets from nomload/assets/logo.svg (run after editing the logo)."""
import os
import sys
from pathlib import Path

if os.name != "nt":  # Windows renders off-screen natively with its system fonts
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

A = ROOT / "nomload" / "assets"


def render(size: int, bg=None) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0) if bg is None else bg)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(A / "logo.svg")).render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def main():
    from nomload.training.qt_render import ensure_qt
    ensure_qt()  # also registers system fonts when Qt has none (offscreen builds)
    render(512).save(str(A / "logo.png"))
    render(128).save(str(A / "logo_128.png"))
    # Windows icon: white rounded tile so it reads on dark taskbars
    icon = QImage(256, 256, QImage.Format.Format_ARGB32)
    icon.fill(QColor(0, 0, 0, 0))
    p = QPainter(icon)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(4, 4, 248, 248), 44, 44)
    QSvgRenderer(str(A / "logo.svg")).render(p, QRectF(14, 14, 228, 228))
    p.end()
    icon.save(str(A / "icon_256.png"))
    icon.save(str(A / "app.ico"))
    # Wordmark for reports (logo + name)
    wm = QImage(1200, 300, QImage.Format.Format_ARGB32)
    wm.fill(QColor(0, 0, 0, 0))
    p = QPainter(wm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(A / "logo.svg")).render(p, QRectF(0, 10, 280, 280))
    f = QFont("Segoe UI")
    f.setPixelSize(128)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1B2A4E"))
    p.drawText(QRectF(300, 20, 900, 160), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "NomLoad")
    f.setPixelSize(52); f.setBold(False); f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 18)
    p.setFont(f)
    p.setPen(QColor("#5A6475"))
    p.drawText(QRectF(306, 180, 900, 80), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "COUNTER")
    p.end()
    wm.save(str(A / "wordmark.png"))
    # combo box chevrons (light + dark theme)
    from PySide6.QtCore import QByteArray
    for name, col in (("chevron_light.png", "#5A6475"), ("chevron_dark.png", "#9AA5BC")):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{col}" '
               'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>')
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, 32, 32))
        p.end()
        img.save(str(A / name))
    print("assets written to", A)


if __name__ == "__main__":
    main()

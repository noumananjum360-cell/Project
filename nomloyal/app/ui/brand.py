"""NomLoyal brand (Devnom family): rounded viewfinder brackets like FabriScan and NomLoad, around a shopping
bag carrying a gold loyalty star. Colours: deep teal + VIP gold."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TEAL = "#0E7C7B"
TEAL_DEEP = "#0A4F57"
NAVY = "#13233A"
GOLD = "#C9A227"
MIST = "#EEF6F6"


def _mark_body(fg: str, accent: str, cut: str) -> str:
    star = ("M60 52.5l4.1 8.3 9.2 1.3-6.6 6.5 1.6 9.1-8.3-4.4-8.3 4.4 1.6-9.1-6.6-6.5 9.2-1.3z")
    return (f'<g fill="none" stroke="{fg}" stroke-width="6.8" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3.4 31V15A11.6 11.6 0 0 1 15 3.4H31"/><path d="M89 3.4H105A11.6 11.6 0 0 1 116.6 15V31"/>'
            '<path d="M3.4 89V105A11.6 11.6 0 0 0 15 116.6H31"/><path d="M116.6 89V105A11.6 11.6 0 0 1 105 116.6H89"/></g>'
            # bag handle + body
            f'<path d="M47 41v-6a13 13 0 0 1 26 0v6" fill="none" stroke="{fg}" stroke-width="6" stroke-linecap="round"/>'
            f'<path d="M30 41h60l-4.5 47.5a6 6 0 0 1-6 5.5H40.5a6 6 0 0 1-6-5.5z" fill="{fg}"/>'
            f'<path d="{star}" fill="{accent}" stroke="{cut}" stroke-width="1.4" stroke-linejoin="round"/>')


def mark_svg(fg: str = TEAL, accent: str = GOLD, cut: str = TEAL) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">{_mark_body(fg, accent, cut)}</svg>'


def icon_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
            f'<rect width="120" height="120" rx="27" fill="{TEAL}"/>'
            f'<g transform="translate(14 14) scale(0.7667)">{_mark_body(MIST, GOLD, MIST)}</g></svg>')


def render(svg: str, size: int, ratio: float = 2.0) -> QImage:
    px = max(1, int(size * ratio))
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, px, px))
    p.end()
    img.setDevicePixelRatio(ratio)
    return img


def mark_pixmap(size: int, fg: str = TEAL, accent: str = GOLD) -> QPixmap:
    return QPixmap.fromImage(render(mark_svg(fg, accent, fg), size))


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(QPixmap.fromImage(render(icon_svg(), s, 1.0)))
    return ic


def wordmark_html(size_pt: float, dark: bool = False) -> str:
    nom = MIST if dark else NAVY
    return (f"<span style='font-family:Poppins; font-weight:700; font-size:{size_pt}pt; color:{nom}'>Nom</span>"
            f"<span style='font-family:Poppins; font-weight:700; font-size:{size_pt}pt; color:{TEAL if not dark else '#3CC7C2'}'>Loyal</span>")


def load_brand_font() -> None:
    from PySide6.QtGui import QFontDatabase
    from app.config import resource_path
    f = resource_path("assets", "fonts", "Poppins-Bold.ttf")
    if f.exists():
        QFontDatabase.addApplicationFont(str(f))

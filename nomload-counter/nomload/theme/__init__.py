"""Theme loading and Qt stylesheet generation (single source: theme.json)."""
from __future__ import annotations

import json
from pathlib import Path

_THEME = None
_MODE = "light"


def load() -> dict:
    global _THEME
    if _THEME is None:
        _THEME = json.loads((Path(__file__).parent / "theme.json").read_text(encoding="utf-8"))
    return _THEME


def mode() -> str:
    return _MODE


def set_mode(m: str):
    global _MODE
    _MODE = "dark" if m == "dark" else "light"


def c(name: str) -> str:
    """Colour by name from brand or the current mode palette."""
    t = load()
    return t[_MODE].get(name) or t["brand"].get(name) or "#FF00FF"


def font_family() -> str:
    f = load()["font"]
    return f["family"]


def stylesheet() -> str:
    t = load()
    p = {**t["brand"], **t[_MODE]}
    f = t["font"]
    base = f["base_px"]
    chevron = (Path(__file__).resolve().parent.parent / "assets" / f"chevron_{_MODE}.png").as_posix()
    return f"""
    * {{ font-family: "{f['family']}", {f['fallback']}; font-size: {base}px; color: {p['text']}; }}
    QMainWindow, QDialog, #Content {{ background: {p['bg']}; }}
    QWidget#Page {{ background: {p['bg']}; }}
    #Sidebar {{ background: {p['sidebar']}; border-right: 1px solid {p['border']}; }}
    #Sidebar QLabel#BrandName {{ font-size: 20px; font-weight: 700; color: {p['primary'] if _MODE == 'light' else p['text']}; }}
    #Sidebar QLabel#BrandSub {{ color: {p['muted']}; font-size: 14px; }}
    QPushButton#Nav {{ text-align: left; padding: 12px 16px; border: none; border-radius: 10px; background: transparent;
        font-size: 15px; }}
    QPushButton#Nav:hover {{ background: {p['nav_hover']}; }}
    QPushButton#Nav:checked {{ background: {p['nav_active']}; font-weight: 600; }}
    QPushButton#Link {{ text-align: left; padding: 6px 12px; border: none; background: transparent; color: {p['muted']}; }}
    QPushButton#Link:hover {{ color: {p['text']}; }}
    QLabel#UserName {{ font-weight: 700; font-size: 15px; }}
    QLabel#Muted, QLabel#UserRole {{ color: {p['muted']}; }}
    QLabel#PageTitle {{ font-size: {f['title_px']}px; font-weight: 700; }}
    QLabel#CardTitle {{ font-size: 16px; font-weight: 700; }}
    QLabel#KpiValue {{ font-size: 28px; font-weight: 700; }}
    QLabel#KpiLabel {{ color: {p['muted']}; }}
    QLabel#BigCount {{ font-size: 46px; font-weight: 800; color: {p['text']}; }}
    QLabel#Plate {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 22px; font-weight: 700;
        background: #FFFFFF; color: #111; border: 2px solid #222; border-radius: 6px; padding: 2px 10px; }}
    QFrame#Card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px; }}
    QFrame#Bay {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px; }}
    QFrame#LoginCard {{ background: #FFFFFF; border-radius: 18px; }}
    QFrame#LoginCard QLabel {{ color: #1A1F2E; }}
    QFrame#LoginCard QLineEdit {{ background: #FFFFFF; color: #1A1F2E; border: 1px solid #E3E6EC; }}
    QFrame#LoginCard QLineEdit:focus {{ border: 1px solid {p['accent']}; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit, QTextEdit {{
        background: {p['input']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 8px 10px; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {p['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
    QDateEdit::drop-down {{ border: none; width: 30px; }}
    QDateEdit::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {p['surface']}; selection-background-color: {p['nav_active']}; }}
    QPushButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 9px 16px; }}
    QPushButton:hover {{ background: {p['surface_alt']}; }}
    QPushButton:disabled {{ color: {p['muted']}; }}
    QPushButton#Primary {{ background: {p['primary']}; color: #FFFFFF; border: none; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {p['primary_hover']}; }}
    QPushButton#Primary:disabled {{ background: {p['chart_soft']}; }}
    QPushButton#Success {{ background: {p['success']}; color: #FFFFFF; border: none; font-weight: 600; }}
    QPushButton#Danger {{ background: {p['danger']}; color: #FFFFFF; border: none; font-weight: 600; }}
    QPushButton#Accent {{ background: {p['accent']}; color: #1B2A4E; border: none; font-weight: 700; }}
    QPushButton#Big {{ font-size: 17px; padding: 14px 22px; }}
    QTableWidget, QTableView, QListWidget, QTreeWidget {{ background: {p['surface']}; border: 1px solid {p['border']};
        border-radius: 10px; gridline-color: {p['border']}; alternate-background-color: {p['surface_alt']};
        selection-background-color: {p['nav_active']}; selection-color: {p['text']}; }}
    QHeaderView::section {{ background: {p['surface_alt']}; border: none; border-bottom: 1px solid {p['border']};
        padding: 8px; font-weight: 600; color: {p['muted']}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; padding: 10px 18px; border: none; color: {p['muted']}; font-weight: 600; }}
    QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 3px solid {p['accent']}; }}
    QProgressBar {{ background: {p['surface_alt']}; border: none; border-radius: 7px; height: 14px; text-align: center;
        color: transparent; }}
    QProgressBar::chunk {{ background: {p['primary'] if _MODE == 'light' else p['chart']}; border-radius: 7px; }}
    QProgressBar#Over::chunk {{ background: {p['danger']}; }}
    QProgressBar#Done::chunk {{ background: {p['success']}; }}
    QStatusBar {{ background: {p['sidebar']}; color: {p['muted']}; border-top: 1px solid {p['border']}; }}
    QStatusBar QLabel {{ color: {p['muted']}; padding: 0 8px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; }}
    QGroupBox {{ border: 1px solid {p['border']}; border-radius: 10px; margin-top: 14px; padding: 12px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
    QToolTip {{ background: {p['primary']}; color: #FFFFFF; border: none; padding: 6px; }}
    QLabel#Pill {{ border-radius: 10px; padding: 3px 10px; font-weight: 600; font-size: 12px; }}
    QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; }}
    QMenu::item:selected {{ background: {p['nav_active']}; }}
    """

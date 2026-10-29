"""Design system - same structure as FabriScan (calm cards, slim sidebar, quiet tables), new palette:
deep teal + VIP gold on a cool off-white, dark navy text."""
from __future__ import annotations

OK, WARN, CRIT, INFO = "#2F8F5B", "#C98A2E", "#C2483A", "#3B6EA5"
ACCENT = "#0E7C7B"       # teal (buttons, selection)
HIGHLIGHT = "#C9A227"    # VIP gold (focus ring, active tab)
CHART = "#0E7C7B"
CHART_2 = "#C9A227"

PALETTES = {
    "light": {"bg": "#F6F8F8", "side": "#EEF3F3", "panel": "#FFFFFF", "border": "#DCE5E5", "text": "#13233A",
              "muted": "#5F6F82", "accent": ACCENT, "accent_hover": "#0B6665", "accent_soft": "#DDEFEE",
              "highlight": HIGHLIGHT, "input": "#FFFFFF", "hover": "#E7EFEF", "sel": "#DDEAEA", "view": "#0F1E2C"},
    "dark": {"bg": "#0F1A24", "side": "#0B141C", "panel": "#16222E", "border": "#253442", "text": "#E5ECF2",
             "muted": "#93A3B5", "accent": "#14A39F", "accent_hover": "#18B6B1", "accent_soft": "#123638",
             "highlight": "#D4AF37", "input": "#0F1A24", "hover": "#1C2A37", "sel": "#22323F", "view": "#070D13"},
}
_current = "light"


def palette(name: str | None = None) -> dict:
    return PALETTES.get(name or _current, PALETTES["light"])


def current() -> str:
    return _current


def set_current(name: str) -> None:
    global _current
    _current = name if name in PALETTES else "light"


def stylesheet(name: str) -> str:
    set_current(name)
    p = palette(name)
    from app.config import resource_path
    chev = resource_path("assets", "icons", f"chevron_{'dark' if name == 'dark' else 'light'}.svg").as_posix()
    return f"""
    * {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', 'Helvetica Neue', Arial; font-size: 10pt;
         color: {p['text']}; }}
    QMainWindow, QDialog, QMessageBox, QWidget#page {{ background: {p['bg']}; }}
    QWidget {{ background: transparent; }}
    QDialog, QMessageBox, QInputDialog, QProgressDialog {{ background: {p['bg']}; }}
    QWidget#sidebar {{ background: {p['side']}; border-right: 1px solid {p['border']}; }}
    QListWidget#nav {{ background: transparent; border: none; outline: none; }}
    QListWidget#nav::item {{ color: {p['text']}; padding: 6px 10px; border-radius: 8px; margin: 1px 10px; border: none; }}
    QListWidget#nav::item:hover:!selected {{ background: {p['hover']}; }}
    QListWidget#nav::item:selected {{ background: {p['accent_soft']}; color: {p['text']}; font-weight: 600; }}
    QPushButton#side {{ background: transparent; border: none; text-align: left; padding: 6px 12px;
         color: {p['muted']}; border-radius: 6px; margin: 0 8px; }}
    QPushButton#side:hover {{ background: {p['hover']}; color: {p['text']}; }}
    QLabel#title {{ font-size: 19pt; font-weight: 600; }}
    QLabel#subtitle {{ font-size: 11pt; font-weight: 600; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#kpiValue {{ font-size: 18pt; font-weight: 600; }}
    QLabel#kpiLabel {{ color: {p['muted']}; font-size: 8.5pt; letter-spacing: 0.4px; }}
    QLabel#banner {{ font-weight: 600; padding: 7px 14px; border-radius: 8px; color: white; }}
    QLabel#demo {{ background: {HIGHLIGHT}; color: #1B1500; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
    QLabel#bigTotal {{ font-size: 26pt; font-weight: 700; }}
    QFrame#loginCard {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 18px; }}
    QFrame#card {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 12px; }}
    QGroupBox {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 12px;
         margin-top: 26px; padding: 14px 12px 12px 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 4px; top: 0px; padding: 0 2px 6px 2px; font-weight: 600; }}
    QPushButton {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 8px;
         padding: 7px 14px; font-weight: 500; }}
    QPushButton:hover {{ background: {p['hover']}; }}
    QPushButton:pressed {{ background: {p['sel']}; }}
    QPushButton:disabled {{ color: {p['muted']}; background: {p['bg']}; }}
    QPushButton:focus {{ border: 1px solid {p['highlight']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: white; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#primary:disabled {{ background: {p['border']}; color: {p['muted']}; }}
    QPushButton#gold {{ background: {HIGHLIGHT}; color: #1B1500; border: none; font-weight: 700; }}
    QPushButton#danger {{ background: {CRIT}; color: white; border: none; font-weight: 600; }}
    QPushButton#danger:hover {{ background: #A93B2F; }}
    QPushButton#danger:disabled {{ background: {p['border']}; color: {p['muted']}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
         background: {p['input']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 8px;
         selection-background-color: {p['accent']}; selection-color: white; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus,
    QTextEdit:focus {{ border: 1px solid {p['highlight']}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {CRIT}; }}
    QComboBox {{ padding-right: 26px; }}
    QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{chev}"); width: 12px; height: 12px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0px; border: none; }}
    QComboBox QAbstractItemView {{ background: {p['panel']}; border: 1px solid {p['border']};
         selection-background-color: {p['sel']}; selection-color: {p['text']}; outline: none; }}
    QTableWidget, QTableView, QListWidget {{ background: {p['panel']}; border: 1px solid {p['border']};
         border-radius: 10px; gridline-color: transparent; outline: none;
         selection-background-color: {p['sel']}; selection-color: {p['text']}; alternate-background-color: {p['bg']}; }}
    QTableWidget::item, QListWidget::item {{ padding: 5px; }}
    QHeaderView::section {{ background: {p['panel']}; color: {p['muted']}; padding: 8px 6px; border: none;
         border-bottom: 1px solid {p['border']}; font-weight: 600; font-size: 9pt; }}
    QTableCornerButton::section {{ background: {p['panel']}; border: none; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ padding: 8px 16px; color: {p['muted']}; border: none; }}
    QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['highlight']}; font-weight: 600; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p['muted']}; border-radius: 5px;
         background: {p['input']}; }}
    QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {p['sel']}; text-align: center; height: 8px; }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 4px; }}
    QStatusBar {{ background: {p['bg']}; color: {p['muted']}; border-top: 1px solid {p['border']}; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
    QToolTip {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 6px; border-radius: 6px; }}
    QMenu {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p['sel']}; }}
    """

"""Reusable widgets: cards, KPI tiles, tables, badges, charts, money input, date range, background tasks."""
from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QDate, QPointF, QRectF, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QProgressDialog, QPushButton, QSizePolicy, QStyledItemDelegate,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.money import fmt, to_minor
from app.ui.icons import icon
from app.ui.theme import CRIT, OK, WARN, palette

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ messages
def show_error(parent, title: str, message: str, exc: BaseException | None = None) -> None:
    if exc is not None and not isinstance(exc, (ValueError,)):
        log.error("%s: %s\n%s", title, message, "".join(traceback.format_exception(exc)))
    QMessageBox.warning(parent, title, message)


def info(parent, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def confirm(parent, title: str, text: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    yes = box.addButton("Yes, continue" if danger else "Yes", QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def guarded(parent, title: str, fn: Callable, *a, **k):
    """Run fn; show service errors (validation, permission, not found) as friendly messages. Returns (ok, result)."""
    from app.security.authentication import AuthError
    from app.security.permissions import PermissionDenied
    from app.services.errors import NotFound, ValidationError
    try:
        return True, fn(*a, **k)
    except (ValidationError, PermissionDenied, NotFound, AuthError, ValueError) as exc:
        QMessageBox.warning(parent, title, str(exc))
    except Exception as exc:  # noqa: BLE001
        show_error(parent, title, f"Something went wrong: {exc}\nDetails were written to the log.", exc)
    return False, None


def open_path(path: str | Path) -> None:
    p = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not open %s: %s", p, exc)


# ------------------------------------------------------------------ layout bits
def card(*widgets: QWidget, layout: str = "v", margins: int = 14, spacing: int = 8) -> QFrame:
    f = QFrame(); f.setObjectName("card")
    lay = QVBoxLayout(f) if layout == "v" else QHBoxLayout(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    return f


def title_label(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("title"); return l


def subtitle(text: str) -> QLabel:
    l = QLabel(text); l.setObjectName("subtitle"); return l


def muted(text: str = "") -> QLabel:
    l = QLabel(text); l.setObjectName("muted"); l.setWordWrap(True); return l


def button(text: str, kind: str = "", icon_name: str | None = None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon_name:
        b.setIcon(icon(icon_name, "#FFFFFF" if kind in ("primary", "danger") else palette()["text"], 16))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class PageHeader(QWidget):
    def __init__(self, title: str, sub: str = ""):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 10); lay.setSpacing(8)
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(title_label(title))
        if sub:
            s = muted(sub); s.setWordWrap(False)
            col.addWidget(s)
        lay.addLayout(col)
        lay.addStretch(1)
        self.actions = lay

    def add(self, w: QWidget) -> QWidget:
        self.actions.addWidget(w)
        return w


class KPITile(QFrame):
    def __init__(self, label: str, value: str = "-"):
        super().__init__()
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(2)
        self.value = QLabel(value); self.value.setObjectName("kpiValue")
        self.label = QLabel(label.upper()); self.label.setObjectName("kpiLabel")
        lay.addWidget(self.value); lay.addWidget(self.label)

    def set(self, value: str, color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color:{color};" if color else "")


class Badge(QLabel):
    """Small rounded tier / status badge."""

    def __init__(self, text: str = "", color: str = "#64748B"):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set(text, color)

    def set(self, text: str, color: str):
        self.setText(text)
        self.setVisible(bool(text))
        self.setStyleSheet(f"background:{color}; color:white; border-radius:8px; padding:2px 10px; font-weight:600;")


class EmptyState(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("muted")
        self.setWordWrap(True)
        self.setMinimumHeight(80)


def demo_badge(text: str = "DEMO DATA") -> QLabel:
    l = QLabel(text); l.setObjectName("demo"); return l


# ------------------------------------------------------------------ tables
def make_table(headers: list[str], stretch: int | None = 0, sortable: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.verticalHeader().setDefaultSectionSize(34)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    h.setHighlightSections(False)
    if stretch is not None:
        h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    t.setSortingEnabled(sortable)
    t.setProperty("sortable", sortable)
    t.setWordWrap(False)
    return t


class MoneyDelegate(QStyledItemDelegate):
    """Shows integer minor units as money; the cell keeps the number so Qt sorts it numerically."""

    def displayText(self, value, locale):
        try:
            return fmt(int(value))
        except (TypeError, ValueError):
            return str(value)


def fill_table(t: QTableWidget, rows: list[list], keys: list | None = None, colors: dict | None = None,
               numeric: set[int] | None = None) -> None:
    """rows: display values. ('money', minor) cells sort numerically and show as money; plain numbers sort as numbers."""
    t.setSortingEnabled(False)
    t.setRowCount(len(rows))
    money_cols = set()
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            it = QTableWidgetItem()
            if isinstance(v, tuple) and v and v[0] == "money":
                it.setData(Qt.DisplayRole, int(v[1] or 0))
                money_cols.add(j)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                it.setData(Qt.DisplayRole, v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                it.setText("" if v is None else str(v))
            if numeric and j in numeric:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if keys is not None and j == 0:
                it.setData(Qt.UserRole, keys[i])
            if colors and (i, j) in colors:
                it.setForeground(QColor(colors[(i, j)]))
                f = it.font(); f.setBold(True); it.setFont(f)
            t.setItem(i, j, it)
    for j in money_cols:
        if not isinstance(t.itemDelegateForColumn(j), MoneyDelegate):
            t.setItemDelegateForColumn(j, MoneyDelegate(t))
    if t.property("sortable") is not False:
        t.setSortingEnabled(True)


def selected_key(t: QTableWidget):
    r = t.currentRow()
    if r < 0:
        return None
    it = t.item(r, 0)
    return it.data(Qt.UserRole) if it else None


# ------------------------------------------------------------------ inputs
class MoneyEdit(QLineEdit):
    """Amount input in major units; value() returns minor units (raises ValueError when invalid)."""

    def __init__(self, placeholder: str = "0"):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAlignment(Qt.AlignRight)
        self.textChanged.connect(self._check)

    def _check(self):
        try:
            self.value()
            ok = True
        except (ValueError, TypeError):
            ok = False
        self.setProperty("invalid", not ok)
        self.style().unpolish(self); self.style().polish(self)

    def value(self) -> int:
        return to_minor(self.text() or "0")

    def set_minor(self, minor: int | None):
        self.setText("" if minor is None else f"{minor / 100:.2f}".rstrip("0").rstrip("."))


class DateRange(QWidget):
    changed = Signal()

    def __init__(self, days: int = 30):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
        self.preset = QComboBox()
        for text, d in (("Today", 0), ("Last 7 days", 6), ("Last 30 days", 29), ("Last 90 days", 89),
                        ("This year", -1), ("Custom", -2)):
            self.preset.addItem(text, d)
        self.d0, self.d1 = QDateEdit(calendarPopup=True), QDateEdit(calendarPopup=True)
        for d in (self.d0, self.d1):
            d.setDisplayFormat("dd MMM yyyy")
            d.dateChanged.connect(self._custom)
        lay.addWidget(self.preset); lay.addWidget(self.d0); lay.addWidget(QLabel("to")); lay.addWidget(self.d1)
        self.preset.currentIndexChanged.connect(self._preset)
        self.preset.setCurrentIndex({0: 0, 6: 1, 29: 2, 89: 3}.get(days - 1 if days else 0, 2))
        self._preset()

    def _preset(self):
        d = self.preset.currentData()
        if d == -2:
            return
        today = QDate.currentDate()
        start = QDate(today.year(), 1, 1) if d == -1 else today.addDays(-d)
        for w in (self.d0, self.d1):
            w.blockSignals(True)
        self.d0.setDate(start); self.d1.setDate(today)
        for w in (self.d0, self.d1):
            w.blockSignals(False)
        self.changed.emit()

    def _custom(self):
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(self.preset.count() - 1)
        self.preset.blockSignals(False)
        self.changed.emit()

    def range(self) -> tuple[dt.date, dt.date]:
        a, b = self.d0.date().toPython(), self.d1.date().toPython()
        return (a, b) if a <= b else (b, a)


# ------------------------------------------------------------------ charts (Qt-native)
class BarChart(QWidget):
    """Bars (optionally a line overlay) with integer-friendly axes and empty state."""

    def __init__(self, money: bool = True, empty: str = "No data for this period"):
        super().__init__()
        self.setMinimumHeight(200)
        self.money = money
        self.empty = empty
        self.labels: list[str] = []
        self.values: list[float] = []
        self.color = palette()["accent"]

    def set_data(self, labels: list[str], values: list[float], color: str | None = None):
        self.labels, self.values = labels, values
        if color:
            self.color = color
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = palette()
        f = QFont(self.font()); f.setPointSizeF(8.5); p.setFont(f)
        r = QRectF(self.rect()).adjusted(58, 10, -10, -26)
        if not self.values or max(self.values) <= 0:
            p.setPen(QColor(pal["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty)
            return
        top = _nice(max(self.values))
        p.setPen(QPen(QColor(pal["border"]), 1))
        for k in range(5):
            y = r.bottom() - r.height() * k / 4
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(pal["muted"]))
            v = top * k / 4
            txt = _short(v / 100) if self.money else f"{v:.0f}"
            p.drawText(QRectF(0, y - 8, r.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, txt)
            p.setPen(QPen(QColor(pal["border"]), 1))
        n = len(self.values)
        slot = r.width() / n
        bw = max(3.0, min(38.0, slot * 0.62))
        import math
        step = max(1, math.ceil(n / max(1.0, r.width() / 64)))
        fm = p.fontMetrics()
        for i, (lab, v) in enumerate(zip(self.labels, self.values)):
            h = r.height() * v / top
            x = r.left() + slot * i + (slot - bw) / 2
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, r.bottom() - h, bw, h), 3, 3)
            p.fillPath(path, QColor(self.color))
            if i % step == 0:
                p.setPen(QColor(pal["muted"]))
                room = slot * step - 4
                p.drawText(QRectF(r.left() + slot * i + slot / 2 - room / 2, r.bottom() + 4, room, 18), Qt.AlignHCenter,
                           fm.elidedText(lab, Qt.ElideRight, int(room)))


def _nice(v: float) -> float:
    import math
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= v:
            return m * e
    return 10 * e


def _short(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1000:
        return f"{v / 1000:.0f}k"
    return f"{v:.0f}"


# ------------------------------------------------------------------ background work
class Task(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.succeeded.emit(self.fn())
        except Exception as exc:  # noqa: BLE001
            log.error("background task failed: %s", "".join(traceback.format_exception(exc)))
            self.failed.emit(str(exc) or type(exc).__name__)


_TASKS: set = set()


def run_task(parent, text: str, fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
             on_fail: Callable[[str], None] | None = None) -> Task:
    """Run slow work (camera test, backup, import) without freezing the window."""
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("Please wait")
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(400)
    dlg.setWindowModality(Qt.WindowModal)
    task = Task(fn)
    _TASKS.add(task)

    def finish():
        dlg.close()
        _TASKS.discard(task)

    task.succeeded.connect(lambda r: (finish(), on_done and on_done(r)))
    task.failed.connect(lambda m: (finish(), (on_fail or (lambda msg: QMessageBox.warning(parent, "Error", msg)))(m)))
    task.start()
    return task


def status_color(status: str) -> str:
    return {"completed": OK, "refunded": CRIT, "partially_refunded": WARN, "voided": "#8A94A6",
            "open": WARN, "acknowledged": OK, "dismissed": "#8A94A6"}.get(status, palette()["text"])


def ts(t: float | None, with_time: bool = True) -> str:
    if not t:
        return "-"
    return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")

"""Helpers shared by pages: sound, thread->UI bridge, file opening."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from nomload.config import assets_dir, reports_dir
from nomload.services.runtime import RuntimeListener


def report_path(name: str) -> Path:
    d = reports_dir() / time.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def open_file(path) -> None:
    path = str(path)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a local report/clip for the user
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def open_folder(path) -> None:
    p = Path(path)
    if sys.platform == "win32" and p.is_file():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        open_file(p if p.is_dir() else p.parent)


class SoundPlayer(QObject):
    """Alarm (looping until acknowledged), chime and beep."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._effects = {}
        try:
            from PySide6.QtMultimedia import QSoundEffect
            for name in ("alarm", "chime", "beep"):
                e = QSoundEffect(self)
                e.setSource(QUrl.fromLocalFile(str(assets_dir() / f"{name}.wav")))
                self._effects[name] = e
        except Exception:  # pragma: no cover - multimedia missing
            self._effects = {}

    def _vol(self) -> float:
        return float(self.settings.get("alert_volume") or 0.9)

    def play(self, name: str):
        if not self.settings.get("sound_alerts"):
            return
        e = self._effects.get(name)
        if e is None:
            QApplication.beep()
            return
        e.setLoopCount(1)
        e.setVolume(self._vol())
        e.play()

    def start_alarm(self):
        if not self.settings.get("sound_alerts"):
            return
        e = self._effects.get("alarm")
        if e is None:
            QApplication.beep()
            return
        e.setLoopCount(-2)  # QSoundEffect.Infinite
        e.setVolume(self._vol())
        e.play()

    def stop_alarm(self):
        e = self._effects.get("alarm")
        if e is not None:
            e.stop()


class QtBridge(QObject, RuntimeListener):
    """Turns calls from bay threads into queued Qt signals (UI thread)."""
    frame_ready = Signal(int, object, dict)
    counted = Signal(int, dict)
    session = Signal(int, object)
    plate_read = Signal(int, str, float, object)
    prompted = Signal(int, str, dict)
    alert = Signal(dict)

    def frame(self, bay_id, frame, status):
        self.frame_ready.emit(bay_id, frame, status)

    def count(self, bay_id, event):
        self.counted.emit(bay_id, event)

    def session_changed(self, bay_id, session_id):
        self.session.emit(bay_id, session_id)

    def plate(self, bay_id, text, confidence, image_path):
        self.plate_read.emit(bay_id, text, confidence, image_path)

    def prompt(self, bay_id, kind, data):
        self.prompted.emit(bay_id, kind, data)

    def on_alert(self, alert: dict):
        self.alert.emit(alert)

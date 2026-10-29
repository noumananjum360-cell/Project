"""Windows notifications through the system tray. Content is fixed and privacy-preserving (see alert_service)."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class TrayNotifier:
    def __init__(self, tray_icon):
        self.tray = tray_icon

    def __call__(self, title: str, message: str):
        from PySide6.QtWidgets import QSystemTrayIcon
        if self.tray is None or not QSystemTrayIcon.isSystemTrayAvailable():
            raise RuntimeError("system tray not available")
        if not QSystemTrayIcon.supportsMessages():
            raise RuntimeError("this system does not support tray notifications")
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 6000)

"""NomLoad Counter entry point.

    python -m nomload            start the desktop app
    python -m nomload --selftest run the end-to-end self test (used after packaging)
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import sys
import time


def run_gui() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase, QIcon
    from PySide6.QtWidgets import QApplication

    from nomload import APP_NAME, VENDOR, i18n, theme
    from nomload.config import assets_dir
    from nomload.services.app import AppServices, setup_logging

    setup_logging()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setOrganizationName(VENDOR)
    qapp.setWindowIcon(QIcon(str(assets_dir() / "app.ico")))
    fams = set(QFontDatabase.families())
    fam = next((f for f in ("Segoe UI", "Inter", "Arial", "DejaVu Sans") if f in fams), qapp.font().family())
    f = QFont(fam)
    f.setPixelSize(14)
    qapp.setFont(f)

    from nomload.ui.login import make_splash
    splash = make_splash()
    splash.show()
    qapp.processEvents()

    def msg(t):
        splash.showMessage("  " + t, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, Qt.GlobalColor.white)
        qapp.processEvents()

    msg("Opening database...")
    app = AppServices()
    theme.set_mode(app.settings.get("theme") or "light")
    i18n.set_language(app.settings.get("language") or "en")
    if i18n.is_rtl():
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    qapp.setStyleSheet(theme.stylesheet())
    msg("Loading AI models...")
    try:
        app.load_models()
    except Exception as e:  # app still opens so the admin can fix settings
        logging.exception("model load failed")
        msg(f"Model error: {e}")
        time.sleep(1.5)
    app.alerts.start_sender()
    msg("Starting...")
    from nomload.ui.main_window import MainWindow
    win = MainWindow(app)
    win.showMaximized()
    splash.finish(win)
    rc = qapp.exec()
    app.shutdown()
    return rc


def main(argv=None) -> int:
    multiprocessing.freeze_support()
    # windowed (console=False) builds have no stdout/stderr
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    ap = argparse.ArgumentParser(prog="NomLoad")
    ap.add_argument("--selftest", action="store_true", help="run the end-to-end self test and exit")
    ap.add_argument("--report", default="", help="write the self-test report to this file")
    args, _rest = ap.parse_known_args(argv)
    if args.selftest:
        from nomload.selftest import run_selftest
        return run_selftest(args.report or None)
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())

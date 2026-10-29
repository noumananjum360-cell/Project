"""NomLoyal entry point.  python main.py  [--selftest]"""
from __future__ import annotations

import os
import sys


def _fonts():
    from PySide6.QtGui import QFont, QFontDatabase
    fams = set(QFontDatabase.families())
    fam = next((f for f in ("Segoe UI", "Inter", "Arial", "DejaVu Sans") if f in fams), None)
    if fam:
        f = QFont(fam); f.setPointSizeF(10)
        return f
    return None


def run_gui() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("NomLoyal"); app.setOrganizationName("Devnom")
    f = _fonts()
    if f:
        app.setFont(f)
    from app.context import AppContext, setup_logging
    from app.ui import brand
    log_path = setup_logging()
    app.setWindowIcon(brand.app_icon())
    try:
        ctx = AppContext()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.exception("startup failed")
        QMessageBox.critical(None, "NomLoyal", f"NomLoyal could not open its database:\n{exc}\n\nLog: {log_path}")
        return 1
    from app.ui.main_window import MainWindow
    win = MainWindow(ctx)
    win.fit_to_screen()
    rc = app.exec()
    ctx.close()
    return rc


def selftest() -> int:
    """Headless check used by build.bat: database, migrations, a sale, a refund and VIP."""
    import tempfile
    os.environ["NOMLOYAL_HOME"] = tempfile.mkdtemp(prefix="nomloyal_selftest_")
    from app.context import AppContext
    from app.models import CartLine
    from app.money import to_minor
    ctx = AppContext()
    ctx.auth.create("selftest", "Selftest123", "Admin", first_run=True)
    ctx.auth.login("selftest", "Selftest123")
    pid = ctx.products.save("T-1", "Test saree", "Sarees", to_minor("50000"), None, 5)
    c = ctx.customers.create("Self Test", "03000000000", data_consent=True)
    sid = ctx.sales.checkout([CartLine(pid, 1)], "Cash", c.id, "phone")
    assert ctx.customers.get(c.id).tier == "VIP"
    ctx.sales.refund(sid, {ctx.sales.get(sid)["items"][0]["id"]: 1}, "selftest")
    assert ctx.customers.get(c.id).tier is None
    import cv2  # noqa: F401  (bundled)
    import qrcode  # noqa: F401
    from PySide6.QtWidgets import QApplication  # noqa: F401
    ctx.close()
    print("SELFTEST OK")
    return 0


def main() -> int:
    # a windowed (no console) build has no stdout/stderr
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if "--selftest" in sys.argv:
        report = None
        if "--report" in sys.argv:
            report = sys.argv[sys.argv.index("--report") + 1]
        try:
            rc = selftest()
            msg = "SELFTEST OK"
        except Exception as exc:  # noqa: BLE001
            import traceback
            rc, msg = 1, "SELFTEST FAILED\n" + traceback.format_exc()
        if report:
            with open(report, "w", encoding="utf-8") as f:
                f.write(msg + "\n")
        return rc
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())

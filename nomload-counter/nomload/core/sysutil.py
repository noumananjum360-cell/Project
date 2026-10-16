"""Small OS helpers."""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback

log = logging.getLogger(__name__)


def raise_ui_thread_priority():
    """Give the window's thread priority over camera decoding and AI threads (Windows).

    Raising the UI thread (rather than lowering the workers) avoids a worker holding
    Python's interpreter lock being starved while the window waits for that lock.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetThreadPriority(k.GetCurrentThread(), 1)  # THREAD_PRIORITY_ABOVE_NORMAL
    except Exception:  # never fatal
        pass


def disable_power_throttling():
    """Opt out of Windows 11 power throttling (EcoQoS).

    On Intel 12th-gen+ laptops Windows otherwise moves the app to the slow efficiency
    cores at low clock speed (especially on battery), and the counting falls behind.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class State(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

        st = State(1, 0x1, 0)  # control EXECUTION_SPEED, state off = never throttle
        k = ctypes.windll.kernel32
        k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(st), ctypes.sizeof(st))  # ProcessPowerThrottling
    except Exception:  # Windows 10 before 1709 etc.
        pass


def free_disk_gb(path) -> float:
    import shutil
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return 999.0


class UiWatchdog(threading.Thread):
    """Logs where the UI thread was stuck whenever it stops responding for a while."""

    def __init__(self, limit_s: float = 2.0):
        super().__init__(daemon=True, name="ui-watchdog")
        self.limit = limit_s
        self.beat = time.monotonic()
        self.main_id = threading.main_thread().ident

    def alive(self):  # called from a UI timer
        self.beat = time.monotonic()

    def run(self):
        reported = False
        while True:
            time.sleep(0.5)
            stalled = time.monotonic() - self.beat
            if stalled > self.limit and not reported:
                reported = True
                frame = sys._current_frames().get(self.main_id)
                stack = "".join(traceback.format_stack(frame)) if frame else "?"
                log.warning("UI not responding for %.1f s. UI thread is at:\n%s", stalled, stack)
            elif stalled <= self.limit and reported:
                reported = False
                log.warning("UI responsive again")

"""Small OS helpers."""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback

log = logging.getLogger(__name__)


def lower_thread_priority():
    """Run the calling worker thread below normal priority (Windows).

    Camera decoding and AI counting then yield to the window, so the UI stays
    responsive even when the CPU is fully used.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetThreadPriority(k.GetCurrentThread(), -1)  # THREAD_PRIORITY_BELOW_NORMAL
    except Exception:  # never fatal
        pass


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

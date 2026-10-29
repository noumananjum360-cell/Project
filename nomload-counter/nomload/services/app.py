"""Composition root: builds every service once and owns the bay runtimes."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from nomload.config import bundled_models_dir, data_home, db_path, logs_dir, user_models_dir
from nomload.core.detector import ModelRegistry
from nomload.core.plates import load_ocr
from nomload.data.db import Database
from nomload.licensing.license import LicenseManager
from nomload.services.alerts import AlertCenter
from nomload.services.bays import BayService
from nomload.services.catalog import GatePassService, ProductService
from nomload.services.context import AuthService, Settings, User, audit
from nomload.services.reports import ReportService, Stats
from nomload.services.runtime import BayRuntime, RuntimeListener
from nomload.services.sessions import SessionService

log = logging.getLogger(__name__)


def setup_logging():
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(logs_dir() / "nomload.log", maxBytes=5_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    root.addHandler(sh)


class AppServices:
    def __init__(self, path: str | Path | None = None):
        self.db = Database(path or db_path())
        self.settings = Settings(self.db)
        self.auth = AuthService(self.db)
        self.products = ProductService(self.db)
        self.gate_passes = GatePassService(self.db, self.products)
        self.bays = BayService(self.db)
        self.sessions = SessionService(self.db, self.settings, self.products, self.gate_passes)
        self.alerts = AlertCenter(self.db, self.settings)
        self.license = LicenseManager(data_home(), self.db)
        self.reports = ReportService(self.db, self.settings, self.sessions, self.license.status)
        self.stats = Stats(self.db)
        self.registry = ModelRegistry()
        self.ocr = None
        self.runtimes: dict[int, BayRuntime] = {}
        self.user: User | None = None
        self.auth.ensure_default_admin()
        self.products.ensure_defaults()

    # ------------------------------------------------------------------ models
    def model_path(self) -> Path:
        p = self.settings.get("detector_model")
        if p and Path(p).exists():
            return Path(p)
        active = user_models_dir() / "active_detector.onnx"
        if active.exists():
            return active
        return bundled_models_dir() / "starter_detector.onnx"

    def load_models(self):
        s = self.settings
        self.registry.load(self.model_path(), use_gpu=bool(s.get("use_gpu")), threads=int(s.get("inference_threads") or 0),
                           conf_threshold=float(s.get("detector_conf") or 0.35))
        try:
            self.ocr = load_ocr(s.all())
        except Exception:
            log.exception("OCR model failed to load")
            self.ocr = None

    def activate_model(self, path: str | Path, user: User):
        """Hot-swap the detector used by all running bays."""
        det = self.registry.load(path, use_gpu=bool(self.settings.get("use_gpu")),
                                 threads=int(self.settings.get("inference_threads") or 0),
                                 conf_threshold=float(self.settings.get("detector_conf") or 0.35))
        self.settings.set("detector_model", str(path))
        audit(self.db, user, "model_activated", "model", Path(path).name, det.info())
        return det

    # ------------------------------------------------------------------ bays
    def allowed_bays(self) -> int:
        st = self.license.status()
        return st.max_bays if st.usable else 0

    def start_bays(self, listener: RuntimeListener | None = None):
        self.stop_bays()
        limit = self.allowed_bays()
        for i, bay in enumerate(self.bays.list(active_only=True)):
            if i >= limit:
                log.warning("Bay %s not started: licence allows %d bay(s)", bay.name, limit)
                continue
            rt = BayRuntime(self, bay, listener)
            self.runtimes[bay.id] = rt
            rt.start()

    def stop_bays(self, wait: float = 0.0):
        """Signal every bay to stop. Threads are daemons; ``wait`` > 0 joins them (used on exit)."""
        rts = list(self.runtimes.values())
        self.runtimes.clear()
        for rt in rts:
            rt.shutdown()
        if wait:
            for rt in rts:
                rt.join(timeout=wait)

    def shutdown(self):
        self.stop_bays(wait=2.0)
        self.alerts.stop()

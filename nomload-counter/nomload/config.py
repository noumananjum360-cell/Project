"""Filesystem locations and static configuration.

Everything the app writes lives under a single data directory so that a
backup is just a folder copy. On Windows this is %PROGRAMDATA%\\Devnom\\NomLoad
(shared by all Windows users of the PC); it can be overridden with the
NOMLOAD_HOME environment variable (used by tests and portable installs).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Detector class vocabulary used by the starter model. Custom models carry their
# own class list in ONNX metadata; this is only the default.
DEFAULT_CLASSES = ["bag", "carton", "crate", "pack", "person", "truck", "plate"]
COUNTABLE_CLASSES = {"bag", "carton", "crate", "pack"}


def _frozen_root() -> Path:
    # PyInstaller one-dir/one-file builds unpack resources under sys._MEIPASS
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))


def resource_root() -> Path:
    """Read-only resources shipped with the app (models, assets, samples)."""
    if getattr(sys, "frozen", False):
        return _frozen_root()
    return Path(__file__).resolve().parent.parent


def package_dir() -> Path:
    if getattr(sys, "frozen", False):
        return _frozen_root() / "nomload"
    return Path(__file__).resolve().parent


def assets_dir() -> Path:
    return package_dir() / "assets"


def data_home() -> Path:
    env = os.environ.get("NOMLOAD_HOME")
    if env:
        p = Path(env)
    elif sys.platform == "win32":
        p = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Devnom" / "NomLoad"
    else:
        p = Path.home() / ".nomload"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_home() / "nomload.db"


def evidence_dir() -> Path:
    p = data_home() / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_models_dir() -> Path:
    p = data_home() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def datasets_dir() -> Path:
    p = data_home() / "datasets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    p = data_home() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_home() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def bundled_models_dir() -> Path:
    return resource_root() / "models"


def samples_dir() -> Path:
    return resource_root() / "samples"

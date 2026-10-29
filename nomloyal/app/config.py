"""Paths and environment. All user data lives outside the program folder so upgrades never touch it."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    """Folder with bundled read-only files (assets, templates). Works from source and in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def data_home() -> Path:
    """Writable data folder. NOMLOYAL_HOME overrides it (tests, portable installs)."""
    env = os.environ.get("NOMLOYAL_HOME")
    if env:
        p = Path(env)
    elif sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Devnom" / "NomLoyal"
    else:
        p = Path.home() / ".nomloyal"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_home() / "nomloyal.db"


def sub_dir(name: str) -> Path:
    p = data_home() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def backups_dir() -> Path:
    return sub_dir("backups")


def exports_dir() -> Path:
    return sub_dir("exports")


def logs_dir() -> Path:
    return sub_dir("logs")

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if os.name != "nt":  # Windows renders off-screen natively and keeps its system fonts
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOAD_HOME", str(tmp_path))
    monkeypatch.setenv("NOMLOAD_FINGERPRINT", "test-pc-1")
    return tmp_path


@pytest.fixture()
def app(home):
    from nomload.services.app import AppServices
    a = AppServices()
    a.user = a.auth.login("admin", "admin123")
    yield a
    a.shutdown()
    a.db.close()

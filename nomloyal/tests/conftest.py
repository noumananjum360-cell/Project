import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOYAL_HOME", str(tmp_path / "home"))
    from app.context import AppContext
    c = AppContext(tmp_path / "home" / "test.db")
    c.auth.create("admin", "Admin1234", "Admin", "Store Admin", first_run=True)
    c.auth.login("admin", "Admin1234")
    yield c
    c.close()


@pytest.fixture
def shop(ctx):
    """Catalogue with a saree (50,000), a shirt (2,500) and a taxed perfume (1,000 @ 17%)."""
    from app.money import to_minor
    p = ctx.products
    ids = {"saree": p.save("SA-1", "Silk saree", "Sarees", to_minor("50000"), None, 10),
           "shirt": p.save("SH-1", "Cotton shirt", "Shirts", to_minor("2500"), None, 50),
           "perfume": p.save("PF-1", "Perfume", "Cosmetics", to_minor("1000"), 1700, 20)}
    return ids


def make_staff(ctx, role, name=None):
    name = name or role.lower()
    ctx.auth.create(name, "Passw0rd!", role, name)
    return ctx.auth.get(ctx.db.scalar("SELECT id FROM staff_users WHERE username=?", (name,)))

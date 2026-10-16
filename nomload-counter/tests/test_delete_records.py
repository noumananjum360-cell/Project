import sqlite3

import pytest

from nomload.services.context import User
from nomload.services.sessions import SessionError


def _gp(app, number="GP-D1", qty=5):
    flour = app.products.by_name("Flour 50kg bag")
    return app.gate_passes.create(app.user, number, [(flour.id, qty)], "LES-1")


def test_unused_gate_pass_is_removed(app):
    gid = _gp(app)
    app.gate_passes.delete(app.user, gid, "entered twice")
    assert app.db.scalar("SELECT COUNT(*) FROM gate_passes WHERE id=?", (gid,)) == 0
    assert app.db.scalar("SELECT COUNT(*) FROM gate_pass_items WHERE gate_pass_id=?", (gid,)) == 0
    _gp(app)  # same number can be entered again


def test_used_gate_pass_is_hidden_and_history_kept(app):
    bid = app.bays.save_bay(app.user, "B")
    gid = _gp(app)
    sid = app.sessions.start(bid, app.user, gid)
    app.sessions.close(sid, app.user)
    app.gate_passes.delete(app.user, gid, "wrong customer")
    assert all(g.id != gid for g in app.gate_passes.list(()))
    assert app.gate_passes.by_number("GP-D1") is None
    assert app.sessions.summary(sid).gate_pass is not None      # the truck still shows its gate pass
    _gp(app)                                                    # number reusable


def test_gate_pass_delete_rules(app):
    bid = app.bays.save_bay(app.user, "B")
    gid = _gp(app)
    app.sessions.start(bid, app.user, gid)
    with pytest.raises(ValueError):
        app.gate_passes.delete(app.user, gid)                   # loading now
    with pytest.raises(ValueError):
        app.gate_passes.delete(User(5, "c", "", "clerk"), _gp(app, "GP-D2"))
    assert app.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='gate_pass_deleted'") == 0


def test_delete_history_sessions(app):
    bid = app.bays.save_bay(app.user, "B")
    sids = []
    for _ in range(3):
        s = app.sessions.start(bid, app.user)
        app.sessions.close(s, app.user)
        sids.append(s)
    for s in sids[:2]:
        app.sessions.soft_delete(s, app.user, "test trucks before go-live")
    assert [r["id"] for r in app.sessions.search()] == [sids[2]]
    assert app.stats.today()["trucks"] == 1
    active = app.sessions.start(bid, app.user)
    with pytest.raises(SessionError):
        app.sessions.soft_delete(active, app.user, "x")


def test_old_database_is_upgraded(home):
    from nomload.config import db_path
    con = sqlite3.connect(db_path())
    con.execute("CREATE TABLE gate_passes (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL UNIQUE, "
                "vehicle_no TEXT NOT NULL DEFAULT '', customer TEXT NOT NULL DEFAULT '', driver_name TEXT NOT NULL "
                "DEFAULT '', driver_phone TEXT NOT NULL DEFAULT '', destination TEXT NOT NULL DEFAULT '', status TEXT "
                "NOT NULL DEFAULT 'open', source TEXT NOT NULL DEFAULT 'manual', notes TEXT NOT NULL DEFAULT '', "
                "created_by INTEGER, created_at REAL NOT NULL)")
    con.execute("INSERT INTO gate_passes(number, created_at) VALUES ('OLD-1', 0)")
    con.commit()
    con.close()
    from nomload.services.app import AppServices
    a = AppServices()
    assert a.gate_passes.by_number("OLD-1") is not None
    a.db.close()

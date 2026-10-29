import sqlite3

import pytest

from nomload.data import crypto


def test_audit_log_append_only(app):
    with pytest.raises(sqlite3.DatabaseError):
        app.db.execute("DELETE FROM audit_log")
    with pytest.raises(sqlite3.DatabaseError):
        app.db.execute("UPDATE audit_log SET action='x'")


def test_counted_records_cannot_be_deleted(app):
    bid = app.bays.save_bay(app.user, "B")
    sid = app.sessions.start(bid, app.user)
    app.sessions.add_event(sid, "bag", 1, 0.9, False)
    for sql in ("DELETE FROM count_events", "DELETE FROM sessions"):
        with pytest.raises(sqlite3.DatabaseError):
            app.db.execute(sql)


def test_soft_delete_admin_only(app):
    from nomload.services.context import User
    from nomload.services.sessions import SessionError
    bid = app.bays.save_bay(app.user, "B")
    sid = app.sessions.start(bid, app.user)
    app.sessions.close(sid, app.user)
    with pytest.raises(SessionError):
        app.sessions.soft_delete(sid, User(9, "c", "", "clerk"), "x")
    app.sessions.soft_delete(sid, app.user, "test session")
    assert not app.sessions.search()
    assert app.sessions.search(include_deleted=True)


def test_password_hashing():
    h = crypto.hash_secret("s3cret!")
    assert h.startswith("scrypt$") and "s3cret" not in h
    assert crypto.verify_secret("s3cret!", h) and not crypto.verify_secret("wrong", h)


def test_sensitive_fields_encrypted_at_rest(app):
    from nomload.core.video import SourceSpec
    bid = app.bays.save_bay(app.user, "B")
    app.bays.save_camera(app.user, bid, "cam", "count", SourceSpec("rtsp", "rtsp://admin:TopSecret@10.0.0.5:554/x"))
    raw = app.db.scalar("SELECT source FROM cameras")
    assert raw.startswith("enc:") and "TopSecret" not in raw
    assert app.bays.list()[0].cameras[0].source.uri.endswith("10.0.0.5:554/x")
    app.settings.set("smtp_password", "mailpass")
    assert "mailpass" not in app.db.scalar("SELECT value FROM settings WHERE key='smtp_password'")
    app.settings._cache.clear()
    assert app.settings.get("smtp_password") == "mailpass"
    flour = app.products.by_name("Flour 50kg bag")
    app.gate_passes.create(app.user, "GP-E", [(flour.id, 1)], driver_phone="0300-1112223")
    assert "0300" not in app.db.scalar("SELECT driver_phone FROM gate_passes")


def test_login_lockout(app):
    from nomload.services.context import AuthError
    for _ in range(5):
        with pytest.raises(AuthError):
            app.auth.login("admin", "bad")
    with pytest.raises(AuthError, match="Too many"):
        app.auth.login("admin", "admin123")


def test_last_admin_cannot_be_disabled(app):
    from nomload.services.context import AuthError
    with pytest.raises(AuthError):
        app.auth.update_user(app.user.id, app.user, active=0)


def test_every_action_audited(app):
    bid = app.bays.save_bay(app.user, "B")
    sid = app.sessions.start(bid, app.user)
    app.sessions.close(sid, app.user)
    acts = {r["action"] for r in app.db.q("SELECT action FROM audit_log")}
    assert {"login", "bay_created", "session_started", "session_closed"} <= acts

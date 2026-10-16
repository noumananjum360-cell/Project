import pytest

from nomload.core.video import SourceSpec


def test_delete_camera(app):
    bid = app.bays.save_bay(app.user, "Bay 1")
    cid = app.bays.save_camera(app.user, bid, "cam", "count", SourceSpec("usb", "0"))
    app.bays.delete_camera(app.user, cid)
    assert app.bays.get(bid).cameras == []
    assert app.db.scalar("SELECT COUNT(*) FROM audit_log WHERE action='camera_deleted'") == 1


def test_delete_bay_without_history_is_removed(app):
    bid = app.bays.save_bay(app.user, "Bay X")
    app.bays.save_camera(app.user, bid, "cam", "count", SourceSpec("usb", "0"))
    app.bays.delete_bay(app.user, bid)
    assert app.db.scalar("SELECT COUNT(*) FROM bays WHERE id=?", (bid,)) == 0
    assert app.db.scalar("SELECT COUNT(*) FROM cameras WHERE bay_id=?", (bid,)) == 0


def test_delete_bay_with_history_keeps_sessions(app):
    bid = app.bays.save_bay(app.user, "Bay 1")
    sid = app.sessions.start(bid, app.user)
    app.sessions.close(sid, app.user)
    app.bays.delete_bay(app.user, bid)
    assert app.bays.get(bid) is None and app.bays.count() == 0
    assert app.sessions.summary(sid).bay_name.startswith("Bay 1")      # history still readable
    app.bays.save_bay(app.user, "Bay 1")                               # name can be reused


def test_cannot_delete_while_loading(app):
    bid = app.bays.save_bay(app.user, "Bay 1")
    cid = app.bays.save_camera(app.user, bid, "cam", "count", SourceSpec("usb", "0"))
    app.sessions.start(bid, app.user)
    with pytest.raises(ValueError):
        app.bays.delete_bay(app.user, bid)
    with pytest.raises(ValueError):
        app.bays.delete_camera(app.user, cid)

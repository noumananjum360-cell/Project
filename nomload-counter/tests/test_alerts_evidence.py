from pathlib import Path

from nomload.services import evidence


def test_remote_alerts_queue_when_offline_and_send_later(app, monkeypatch):
    app.settings.set("email_enabled", True)
    app.settings.set("email_to", "owner@example.com")
    app.settings.set("remote_events", ["mismatch"])
    app.alerts.raise_alert("mismatch", "Bay 1: 5 bags short")
    app.alerts.raise_alert("low_confidence", "not selected for remote")
    assert app.alerts.pending_count() == 1
    sent = []
    monkeypatch.setattr(app.alerts, "online", lambda *a, **k: False)
    assert app.alerts.flush() == 0 and app.alerts.pending_count() == 1
    monkeypatch.setattr(app.alerts, "online", lambda *a, **k: True)
    monkeypatch.setattr(app.alerts, "_send_email", lambda to, s, b, a: sent.append((to, s, b)))
    assert app.alerts.flush() == 1 and app.alerts.pending_count() == 0
    assert sent[0][0] == "owner@example.com" and "short" in sent[0][2]


def test_failed_send_retries(app, monkeypatch):
    app.settings.set("sms_enabled", True)
    app.settings.set("sms_to", "03001234567")
    app.alerts.queue_remote("t", "b")
    monkeypatch.setattr(app.alerts, "online", lambda *a, **k: True)
    assert app.alerts.flush() == 0     # template missing -> error, stays queued
    row = app.db.one("SELECT * FROM remote_queue")
    assert row["status"] == "queued" and row["attempts"] == 1 and row["last_error"]


def test_evidence_hash_detects_tampering(app, tmp_path):
    bid = app.bays.save_bay(app.user, "B")
    sid = app.sessions.start(bid, app.user)
    f = evidence.session_dir(sid) / "snap.jpg"
    f.write_bytes(b"original image bytes" * 100)
    evidence.register(app.db, sid, "snapshot", f)
    assert evidence.verify_session(app.db, sid)[0]["status"] == "ok"
    f.write_bytes(b"edited image bytes" * 100)
    assert evidence.verify_session(app.db, sid)[0]["status"] == "modified"
    f.unlink()
    assert evidence.verify_session(app.db, sid)[0]["status"] == "missing"


def test_evidence_pack(app, tmp_path):
    import zipfile
    bid = app.bays.save_bay(app.user, "B")
    sid = app.sessions.start(bid, app.user)
    f = evidence.session_dir(sid) / "clip.mp4"
    f.write_bytes(b"x" * 5000)
    evidence.register(app.db, sid, "clip", f)
    z = evidence.build_evidence_pack(app.db, sid, tmp_path / "p.zip")
    names = zipfile.ZipFile(z).namelist()
    assert "manifest.json" in names and "video/clip.mp4" in names

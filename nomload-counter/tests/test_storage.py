import time

from nomload.services import evidence, storage
from nomload.services.context import User


def _session_with_clip(app, age_days):
    bid = app.bays.save_bay(app.user, f"B{age_days}")
    sid = app.sessions.start(bid, app.user)
    app.sessions.close(sid, app.user)
    old = time.time() - age_days * 86400
    app.db.execute("UPDATE sessions SET started_at=? WHERE id=?", (old, sid))
    clip = evidence.session_dir(sid, old) / "clip.mp4"
    clip.write_bytes(b"0" * 5000)
    evidence.register(app.db, sid, "clip", clip)
    return sid, clip


def test_purge_old_videos_keeps_recent_and_marks_removed(app):
    old_sid, old_clip = _session_with_clip(app, 40)
    new_sid, new_clip = _session_with_clip(app, 2)
    n, freed = storage.purge_old_videos(app.db, app.user, 30)
    assert (n, freed) == (1, 5000)
    assert not old_clip.exists() and new_clip.exists()
    # deliberate cleanup shows as "removed", never as missing/tampered
    assert [r["status"] for r in evidence.verify_session(app.db, old_sid)] == ["removed"]
    assert [r["status"] for r in evidence.verify_session(app.db, new_sid)] == ["ok"]
    acts = {r["action"] for r in app.db.q("SELECT action FROM audit_log")}
    assert "evidence_videos_purged" in acts


def test_only_admin_can_purge(app):
    import pytest
    with pytest.raises(ValueError):
        storage.purge_old_videos(app.db, User(9, "c", "", "clerk"), 30)


def test_usage_reports_sizes(app):
    _session_with_clip(app, 1)
    u = storage.usage()
    assert u["videos"] >= 5000 and u["free_gb"] > 0


def test_dataset_samples_are_shrunk(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    from nomload.training.dataset import Dataset
    monkeypatch.setenv("NOMLOAD_HOME", str(tmp_path))
    d = Dataset.create("big")
    cv2.imwrite(str(d.images / "phone_000000.jpg"), np.zeros((2160, 3840, 3), np.uint8))
    d.write_labels(d.images / "phone_000000.jpg", [(0, 1920, 1080, 2880, 1620)], 3840, 2160)
    im, boxes = d.samples("all")[0]
    assert im.shape[1] == 640
    assert [round(v) for v in boxes[0][1:]] == [320, 180, 480, 270]

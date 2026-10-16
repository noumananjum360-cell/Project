"""Disk usage of NomLoad data and cleanup of old loading videos."""
from __future__ import annotations

import time
from pathlib import Path

from nomload.config import data_home, datasets_dir, evidence_dir, logs_dir, user_models_dir
from nomload.core.sysutil import free_disk_gb
from nomload.data.db import Database
from nomload.services.context import User, audit


def _size(folder: Path, pattern: str = "*") -> int:
    total = 0
    for p in folder.rglob(pattern):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def usage() -> dict:
    """Bytes used per kind of data, plus free space on the drive (GB)."""
    ev = evidence_dir()
    videos = _size(ev, "*.mp4")
    return {"videos": videos, "photos": _size(ev) - videos, "datasets": _size(datasets_dir()),
            "models": _size(user_models_dir()), "logs": _size(logs_dir()), "free_gb": free_disk_gb(data_home())}


def old_videos(db: Database, days: int) -> list[tuple[int, Path]]:
    """Loading videos of closed sessions older than ``days``."""
    cutoff = time.time() - days * 86400
    out = []
    for r in db.q("SELECT e.session_id, e.path FROM evidence_files e JOIN sessions s ON s.id=e.session_id "
                  "WHERE e.kind='clip' AND s.status<>'active' AND s.started_at < ?", (cutoff,)):
        p = Path(r["path"])
        if p.exists():
            out.append((r["session_id"], p))
    return out


def purge_old_videos(db: Database, actor: User, days: int) -> tuple[int, int]:
    """Delete old loading videos (photos, plate images and records are kept). Returns (files, bytes)."""
    if not actor.can("delete_records"):
        raise ValueError("Only an Admin can delete old videos.")
    if days < 1:
        raise ValueError("Keep at least 1 day of videos.")
    n = freed = 0
    for sid, p in old_videos(db, days):
        try:
            size = p.stat().st_size
            p.unlink()
        except OSError:
            continue
        db.execute("INSERT OR REPLACE INTO evidence_purged(path, purged_at, user_id) VALUES (?,?,?)",
                   (str(p), time.time(), actor.id))
        n += 1
        freed += size
    audit(db, actor, "evidence_videos_purged", "storage", "", {"older_than_days": days, "files": n, "bytes": freed})
    return n, freed

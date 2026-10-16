"""Evidence integrity (SHA-256) and one-click evidence packs."""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from nomload.config import evidence_dir
from nomload.data.crypto import sha256_file
from nomload.data.db import Database


def session_dir(session_id: int, started_at: float | None = None) -> Path:
    day = time.strftime("%Y-%m-%d", time.localtime(started_at or time.time()))
    p = evidence_dir() / day / f"session_{session_id:06d}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def register(db: Database, session_id: int | None, kind: str, path: str | Path) -> str:
    """Hash a finalised evidence file and store the hash. Returns the hex digest."""
    path = Path(path)
    digest = sha256_file(path)
    db.execute("INSERT INTO evidence_files(session_id, kind, path, sha256, size, created_at) VALUES (?,?,?,?,?,?)",
               (session_id, kind, str(path), digest, path.stat().st_size, time.time()))
    return digest


def verify_session(db: Database, session_id: int) -> list[dict]:
    """Re-hash every evidence file of a session. status: ok | modified | missing."""
    out = []
    for r in db.q("SELECT * FROM evidence_files WHERE session_id=? ORDER BY id", (session_id,)):
        p = Path(r["path"])
        if not p.exists():
            st = "missing"
        else:
            st = "ok" if sha256_file(p) == r["sha256"] else "modified"
        out.append({"kind": r["kind"], "path": str(p), "sha256": r["sha256"], "status": st})
    return out


def build_evidence_pack(db: Database, session_id: int, out_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    """Zip clip + PDF summary + snapshots + plate image + a hash manifest."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = db.q("SELECT * FROM evidence_files WHERE session_id=? AND kind<>'pack' ORDER BY id", (session_id,))
    manifest = {"session_id": session_id, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": [], "verification": verify_session(db, session_id)}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r in files:
            p = Path(r["path"])
            if not p.exists():
                continue
            arc = {"clip": "video/", "snapshot": "snapshots/", "plate": "plate/", "report": ""}.get(r["kind"], "other/") + p.name
            z.write(p, arc)
            manifest["files"].append({"file": arc, "sha256": r["sha256"], "kind": r["kind"]})
        if pdf_path and Path(pdf_path).exists():
            z.write(pdf_path, Path(pdf_path).name)
            manifest["files"].append({"file": Path(pdf_path).name, "sha256": sha256_file(pdf_path), "kind": "summary"})
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("README.txt", "NomLoad Counter evidence pack\n\nEvery file is listed in manifest.json with its SHA-256 "
                   "hash as recorded at the time of loading.\nTo verify a file on Windows run:\n"
                   "    certutil -hashfile <file> SHA256\nand compare with the manifest.\n")
    return out_path

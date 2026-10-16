"""SQLite database: schema, migrations and thread-safe access.

Integrity rules are enforced *in the database* with triggers, so they hold
even if someone opens the file with another tool through the app's code
paths: audit log rows can never be changed or deleted, and count events,
sessions and evidence records can never be deleted (sessions are soft
deleted by an Admin, which is itself audited).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('admin','supervisor','clerk')),
    pw_hash TEXT NOT NULL,
    pin_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_pw INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_login REAL
);

CREATE TABLE IF NOT EXISTS bays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    auto_session INTEGER NOT NULL DEFAULT 0,
    config TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bay_id INTEGER NOT NULL REFERENCES bays(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'count' CHECK (role IN ('count','plate')),
    source TEXT NOT NULL,              -- encrypted JSON (may contain RTSP password)
    geometry TEXT NOT NULL DEFAULT '{}',
    reference BLOB,                    -- JPEG of the calibrated view (tamper reference)
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sku TEXT NOT NULL DEFAULT '',
    detector_class TEXT NOT NULL DEFAULT 'bag',
    units_per_detection INTEGER NOT NULL DEFAULT 1,
    tolerance_units INTEGER,
    tolerance_pct REAL,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS product_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    path TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    vehicle_no TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    driver_name TEXT NOT NULL DEFAULT '',
    driver_phone TEXT NOT NULL DEFAULT '',   -- encrypted
    destination TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','loading','completed','cancelled')),
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS gate_pass_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_pass_id INTEGER NOT NULL REFERENCES gate_passes(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    expected_qty INTEGER NOT NULL CHECK (expected_qty >= 0)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bay_id INTEGER NOT NULL REFERENCES bays(id),
    gate_pass_id INTEGER REFERENCES gate_passes(id),
    plate_text TEXT NOT NULL DEFAULT '',
    plate_confidence REAL,
    plate_image TEXT,
    plate_corrected_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','cleared','mismatch','released','cancelled')),
    started_at REAL NOT NULL,
    ended_at REAL,
    started_by INTEGER REFERENCES users(id),
    closed_by INTEGER REFERENCES users(id),
    auto_started INTEGER NOT NULL DEFAULT 0,
    released_by INTEGER REFERENCES users(id),
    release_reason TEXT,
    clip_path TEXT,
    result TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS ix_sessions_plate ON sessions(plate_text);

CREATE TABLE IF NOT EXISTS count_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    product_id INTEGER REFERENCES products(id),
    cls TEXT NOT NULL,
    direction INTEGER NOT NULL CHECK (direction IN (-1, 1)),
    units INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL,
    review TEXT NOT NULL DEFAULT 'auto' CHECK (review IN ('auto','pending','accepted','rejected','manual')),
    reason TEXT NOT NULL DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id),
    ts REAL NOT NULL,
    track_id INTEGER,
    snapshot TEXT,
    box TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_session ON count_events(session_id);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    bay_id INTEGER,
    session_id INTEGER,
    message TEXT NOT NULL,
    acknowledged_by INTEGER REFERENCES users(id),
    acknowledged_at REAL
);
CREATE INDEX IF NOT EXISTS ix_alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS remote_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,       -- encrypted
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    attachment TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_at REAL
);

CREATE TABLE IF NOT EXISTS evidence_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evidence_session ON evidence_files(session_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts);

CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON count_events
BEGIN SELECT RAISE(ABORT, 'count events cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS sessions_no_delete BEFORE DELETE ON sessions
BEGIN SELECT RAISE(ABORT, 'sessions cannot be deleted; use soft delete'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence_files
BEGIN SELECT RAISE(ABORT, 'evidence records cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE OF sha256, path ON evidence_files
BEGIN SELECT RAISE(ABORT, 'evidence hashes cannot be changed'); END;
"""


class Database:
    """One SQLite file, one connection per thread, serialised writes."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        with self.tx() as c:
            c.executescript(SCHEMA)
            # migrations for databases created by earlier versions
            cols = {r[1] for r in c.execute("PRAGMA table_info(gate_passes)")}
            if "deleted" not in cols:
                c.execute("ALTER TABLE gate_passes ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
            cols = {r[1] for r in c.execute("PRAGMA table_info(products)")}
            if "deleted" not in cols:
                c.execute("ALTER TABLE products ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
            c.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            c.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('created_at', ?)", (str(time.time()),))

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self):
        with self._write_lock:
            c = self.conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                yield c
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, args).fetchall()

    def one(self, sql: str, args=()) -> sqlite3.Row | None:
        return self.conn().execute(sql, args).fetchone()

    def scalar(self, sql: str, args=()):
        r = self.conn().execute(sql, args).fetchone()
        return r[0] if r else None

    def execute(self, sql: str, args=()) -> int:
        with self.tx() as c:
            cur = c.execute(sql, args)
            return cur.lastrowid

    def close(self):
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    # convenience for settings
    def get_setting(self, key: str, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        if r is None:
            return default
        try:
            return json.loads(r["value"])
        except Exception:
            return r["value"]

    def set_setting(self, key: str, value):
        self.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value)))

"""SQLite access: one connection per thread, foreign keys on, WAL, serialised write transactions."""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


class DatabaseError(Exception):
    """A database problem shown to the user in plain words."""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._all: list[sqlite3.Connection] = []
        from app.migrations import migrate
        migrate(self)

    # ------------------------------------------------------------------ connections
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            if self.path != ":memory:":
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
            self._all.append(c)
        return c

    def close(self):
        for c in self._all:
            try:
                c.close()
            except sqlite3.Error:
                pass
        self._all.clear()
        self._local = threading.local()

    # ------------------------------------------------------------------ transactions
    @contextmanager
    def tx(self):
        """All-or-nothing write transaction. Nested calls join the outer transaction."""
        with self._write_lock:
            c = self.conn()
            depth = getattr(self._local, "depth", 0)
            if depth == 0:
                c.execute("BEGIN IMMEDIATE")
            self._local.depth = depth + 1
            try:
                yield c
            except BaseException:
                self._local.depth = depth
                if depth == 0:
                    c.execute("ROLLBACK")
                raise
            else:
                self._local.depth = depth
                if depth == 0:
                    c.execute("COMMIT")

    # ------------------------------------------------------------------ helpers (parameterised only)
    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, args).fetchall()

    def one(self, sql: str, args=()) -> sqlite3.Row | None:
        return self.conn().execute(sql, args).fetchone()

    def scalar(self, sql: str, args=(), default=None):
        r = self.conn().execute(sql, args).fetchone()
        return default if r is None or r[0] is None else r[0]

    def execute(self, sql: str, args=()) -> int:
        with self.tx() as c:
            return c.execute(sql, args).lastrowid

    def integrity_ok(self) -> bool:
        return self.scalar("PRAGMA integrity_check") == "ok"

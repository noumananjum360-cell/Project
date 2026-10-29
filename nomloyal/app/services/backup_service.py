"""Backup and restore of the SQLite database with validation. The active database is never overwritten by
a backup and a safety copy is always made before a restore."""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

from app.config import backups_dir
from app.migrations import SCHEMA_VERSION
from app.security.audit import audit
from app.services.errors import ValidationError

REQUIRED_TABLES = {"customers", "products", "sales", "sale_items", "refunds", "staff_users", "customer_visits",
                   "alerts", "audit_log", "app_settings", "consent_records", "import_jobs", "vip_tiers"}


def validate_backup(path: str | Path) -> dict:
    """Open a backup read-only and check integrity, tables and schema version."""
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1024:
        raise ValidationError("The backup file does not exist or is empty.")
    try:
        c = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValidationError("The backup file is damaged (integrity check failed).")
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = REQUIRED_TABLES - tables
            if missing:
                raise ValidationError("This is not a NomLoyal backup (missing: " + ", ".join(sorted(missing)) + ").")
            version = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
            if version > SCHEMA_VERSION:
                raise ValidationError("This backup was made by a newer NomLoyal version.")
            info = {"version": version,
                    "customers": c.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                    "sales": c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                    "admins": c.execute("SELECT COUNT(*) FROM staff_users WHERE role='Admin' AND active=1").fetchone()[0]}
        finally:
            c.close()
    except sqlite3.DatabaseError as exc:
        raise ValidationError(f"The file is not a valid database: {exc}") from exc
    if not info["admins"]:
        raise ValidationError("The backup has no active Admin account - you would be locked out.")
    return info


class BackupService:
    def __init__(self, db, auth):
        self.db = db
        self.auth = auth

    def backup(self, dest: str | Path | None = None) -> Path:
        user = self.auth.require("backup.manage")
        dest = Path(dest) if dest else backups_dir() / f"nomloyal_{time.strftime('%Y%m%d_%H%M%S')}.db"
        if dest.resolve() == Path(self.db.path).resolve():
            raise ValidationError("Choose a different file - this is the live database.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        target = sqlite3.connect(tmp)
        try:
            self.db.conn().backup(target)
        finally:
            target.close()
        validate_backup(tmp)
        tmp.replace(dest)
        audit(self.db, user, "backup_created", "backup", dest.name)
        return dest

    def restore(self, src: str | Path) -> Path:
        """Replace the live data with a validated backup. Returns the safety copy of the previous data.
        The app must be restarted afterwards."""
        user = self.auth.require("backup.manage")
        src = Path(src)
        if src.resolve() == Path(self.db.path).resolve():
            raise ValidationError("This is the live database, not a backup.")
        info = validate_backup(src)
        safety = self.backup(backups_dir() / f"before_restore_{time.strftime('%Y%m%d_%H%M%S')}.db")
        audit(self.db, user, "restore_started", "backup", src.name, info)
        source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
        try:
            with self.db._write_lock:
                source.backup(self.db.conn())
        finally:
            source.close()
        from app.migrations import migrate
        migrate(self.db)                         # bring an older backup up to the current schema
        audit(self.db, user, "restore_completed", "backup", src.name, {"safety_copy": safety.name})
        return safety

    @staticmethod
    def list_backups() -> list[Path]:
        return sorted(backups_dir().glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)

    @staticmethod
    def copy_out(src: Path, dest: str | Path) -> Path:
        dest = Path(dest)
        shutil.copy2(src, dest)
        return dest

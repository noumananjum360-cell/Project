import sqlite3

import pytest

from app.models import CartLine
from app.services.backup_service import validate_backup
from app.services.errors import ValidationError


def test_backup_and_restore(ctx, shop, tmp_path):
    ctx.customers.create("Before Backup", "03001234567", data_consent=True)
    b = ctx.backup.backup(tmp_path / "b.db")
    info = validate_backup(b)
    assert info["customers"] == 1
    ctx.customers.create("After Backup", "03007654321", data_consent=True)
    ctx.sales.checkout([CartLine(shop["shirt"], 1)], "Cash")
    safety = ctx.backup.restore(b)
    assert safety.exists()
    assert [c.full_name for c in ctx.customers.search()] == ["Before Backup"]
    assert ctx.db.scalar("SELECT COUNT(*) FROM sales") == 0
    assert validate_backup(safety)["customers"] == 2          # the replaced data is kept as a safety copy


def test_backup_refuses_live_db_and_garbage(ctx, tmp_path):
    with pytest.raises(ValidationError):
        ctx.backup.backup(ctx.db.path)
    with pytest.raises(ValidationError):
        ctx.backup.restore(ctx.db.path)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"x" * 4096)
    with pytest.raises(ValidationError):
        validate_backup(junk)
    other = tmp_path / "other.db"
    c = sqlite3.connect(other)
    c.execute("CREATE TABLE t(x)")
    c.execute("INSERT INTO t VALUES (zeroblob(5000))")
    c.commit(); c.close()
    with pytest.raises(ValidationError, match="not a NomLoyal"):
        validate_backup(other)


def test_migrations_are_idempotent_and_versioned(tmp_path):
    from app.database import Database
    from app.migrations import SCHEMA_VERSION, migrate
    db = Database(tmp_path / "m.db")
    assert db.scalar("SELECT MAX(version) FROM schema_migrations") == SCHEMA_VERSION
    assert migrate(db) == []
    assert db.scalar("SELECT COUNT(*) FROM vip_tiers") == 4
    db.close()


def test_newer_database_is_refused(tmp_path):
    from app.database import Database, DatabaseError
    db = Database(tmp_path / "n.db")
    db.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (999, 'future', 0)")
    db.close()
    with pytest.raises(DatabaseError):
        Database(tmp_path / "n.db")

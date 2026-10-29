"""Schema migrations. Each migration runs once, in order, inside a transaction.
Never edit a released migration - add a new one instead."""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

M001 = """
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE staff_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('Admin','Manager','Cashier')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until REAL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    last_login_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loyalty_id TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','anonymized')),
    vip_tier TEXT,
    vip_reason TEXT NOT NULL DEFAULT '',
    vip_override_tier TEXT,
    vip_override_reason TEXT NOT NULL DEFAULT '',
    vip_override_by INTEGER REFERENCES staff_users(id),
    vip_override_at REAL,
    vip_updated_at REAL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL
);
CREATE UNIQUE INDEX ux_customers_phone ON customers(phone) WHERE phone IS NOT NULL AND phone <> '';
CREATE INDEX ix_customers_name ON customers(full_name COLLATE NOCASE);
CREATE INDEX ix_customers_status ON customers(status);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    tax_rate_bp INTEGER CHECK (tax_rate_bp IS NULL OR (tax_rate_bp >= 0 AND tax_rate_bp <= 10000)),
    stock_qty INTEGER NOT NULL DEFAULT 0,
    track_stock INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX ix_products_name ON products(name COLLATE NOCASE);
CREATE INDEX ix_products_category ON products(category);

CREATE TABLE import_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_ok INTEGER NOT NULL DEFAULT 0,
    rows_error INTEGER NOT NULL DEFAULT 0,
    rows_duplicate INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]',
    user_id INTEGER REFERENCES staff_users(id),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    link_method TEXT NOT NULL DEFAULT 'none'
        CHECK (link_method IN ('none','loyalty_id','phone','qr','selected','pos_import')),
    cashier_id INTEGER REFERENCES staff_users(id),
    sold_at REAL NOT NULL,
    subtotal INTEGER NOT NULL,
    discount_total INTEGER NOT NULL,
    tax_total INTEGER NOT NULL,
    total INTEGER NOT NULL CHECK (total >= 0),
    invoice_discount INTEGER NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed','partially_refunded','refunded','voided')),
    void_reason TEXT NOT NULL DEFAULT '',
    voided_by INTEGER REFERENCES staff_users(id),
    voided_at REAL,
    source TEXT NOT NULL DEFAULT 'pos' CHECK (source IN ('pos','import','demo')),
    import_job_id INTEGER REFERENCES import_jobs(id),
    notes TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX ix_sales_customer ON sales(customer_id, sold_at);
CREATE INDEX ix_sales_sold_at ON sales(sold_at);
CREATE INDEX ix_sales_status ON sales(status);

CREATE TABLE sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    line_discount INTEGER NOT NULL DEFAULT 0 CHECK (line_discount >= 0),
    invoice_discount_share INTEGER NOT NULL DEFAULT 0,
    tax_rate_bp INTEGER NOT NULL DEFAULT 0,
    line_tax INTEGER NOT NULL DEFAULT 0,
    line_total INTEGER NOT NULL,
    refunded_qty INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_sale_items_sale ON sale_items(sale_id);
CREATE INDEX ix_sale_items_product ON sale_items(product_id);

CREATE TABLE refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refund_no TEXT NOT NULL UNIQUE,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    processed_by INTEGER REFERENCES staff_users(id),
    refunded_at REAL NOT NULL,
    reason TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    method TEXT NOT NULL DEFAULT 'Cash',
    restock INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX ix_refunds_sale ON refunds(sale_id);
CREATE INDEX ix_refunds_at ON refunds(refunded_at);
CREATE TABLE refund_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refund_id INTEGER NOT NULL REFERENCES refunds(id) ON DELETE CASCADE,
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(id),
    qty INTEGER NOT NULL CHECK (qty > 0),
    amount INTEGER NOT NULL CHECK (amount >= 0)
);

CREATE TABLE customer_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    visited_at REAL NOT NULL,
    method TEXT NOT NULL,
    staff_id INTEGER REFERENCES staff_users(id),
    notes TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX ix_visits_customer ON customer_visits(customer_id, visited_at);

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    is_simulated INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','dismissed')),
    handled_by INTEGER REFERENCES staff_users(id),
    handled_at REAL,
    os_notified INTEGER NOT NULL DEFAULT 0,
    os_error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX ix_alerts_status ON alerts(status, created_at);
CREATE INDEX ix_alerts_customer ON alerts(customer_id, kind, created_at);

CREATE TABLE consent_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    consent_type TEXT NOT NULL CHECK (consent_type IN ('data_processing','marketing','biometric')),
    granted INTEGER NOT NULL,
    notice_version TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT 'in_store',
    recorded_by INTEGER REFERENCES staff_users(id),
    recorded_at REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_consent_customer ON consent_records(customer_id, consent_type, recorded_at);

CREATE TABLE vip_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    rank INTEGER NOT NULL,
    min_single_purchase INTEGER,
    min_rolling_spend INTEGER,
    window_months INTEGER NOT NULL DEFAULT 12 CHECK (window_months BETWEEN 1 AND 120),
    color TEXT NOT NULL DEFAULT '#0E7C7B',
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    CHECK (min_single_purchase IS NOT NULL OR min_rolling_spend IS NOT NULL)
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_audit_ts ON audit_log(ts);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;

-- a completed sale is a financial record: it can be voided or refunded, never deleted
CREATE TRIGGER sales_no_delete BEFORE DELETE ON sales WHEN OLD.is_demo = 0
BEGIN SELECT RAISE(ABORT, 'sales cannot be deleted - void or refund them instead'); END;
"""

# default VIP tiers (amounts in paisa): editable in the app
M002_TIERS = [
    ("Bronze", 1, None, 2_500_000, 12, "#A86B3C"),
    ("Silver", 2, None, 5_000_000, 12, "#7D8B99"),
    ("Gold", 3, None, 7_500_000, 12, "#C9A227"),
    ("VIP", 4, 5_000_000, 10_000_000, 12, "#7A3E9D"),
]

MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "initial schema", M001),
    (2, "default VIP tiers", "tiers"),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


def current_version(db) -> int:
    c = db.conn()
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at REAL)")
    return int(db.scalar("SELECT MAX(version) FROM schema_migrations", default=0))


def migrate(db) -> list[int]:
    """Apply pending migrations. Returns the versions applied. Existing data is never dropped."""
    applied = []
    have = current_version(db)
    if have > SCHEMA_VERSION:
        from app.database import DatabaseError
        raise DatabaseError(f"This database was created by a newer NomLoyal (schema {have}). Please update the program.")
    for version, name, body in MIGRATIONS:
        if version <= have:
            continue
        with db.tx() as c:
            if body == "tiers":
                now = time.time()
                for n, rank, single, rolling, months, color in M002_TIERS:
                    c.execute("INSERT OR IGNORE INTO vip_tiers(name, rank, min_single_purchase, min_rolling_spend, "
                              "window_months, color, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                              (n, rank, single, rolling, months, color, now, now))
            else:
                for stmt in _split(body):
                    c.execute(stmt)
            c.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                      (version, name, time.time()))
        log.info("migration %s applied: %s", version, name)
        applied.append(version)
    return applied


def _split(script: str) -> list[str]:
    """Split a script into statements (triggers contain ';' inside BEGIN ... END)."""
    out, cur, depth = [], [], 0
    for line in script.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        cur.append(line)
        up = s.upper()
        if " BEGIN " in f" {up} " or up.endswith(" BEGIN") or " BEGIN SELECT" in up:
            depth += 1
        if depth:
            if up.endswith("END;"):
                depth = 0
                out.append("\n".join(cur)); cur = []
            continue
        if s.endswith(";"):
            out.append("\n".join(cur)); cur = []
    if cur:
        out.append("\n".join(cur))
    return out

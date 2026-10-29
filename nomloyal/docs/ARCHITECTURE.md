# Architecture

```
main.py                    entry point (GUI, --selftest)
app/
  config.py                paths (program files vs. user data)
  database.py              SQLite: one connection per thread, foreign keys, WAL, serialised write transactions
  migrations.py            versioned migrations (schema_migrations table)
  money.py                 integer minor units (paisa), parsing, formatting, percentages
  models.py                dataclasses
  context.py               wires everything (AppContext)
  repositories/            settings_repo (key/value with defaults), customers_repo
  security/                passwords (scrypt), permissions (RBAC), authentication, audit (append-only)
  services/                customer, product, sales (pricing/refunds/voids), vip, alert, privacy, reporting,
                           import (CSV preview/commit/export), backup, receipt (HTML), demo_data
  integrations/            camera_base, camera_opencv (USB/RTSP, reconnect), recognition (provider interface,
                           NoProvider), pos_base, pos_csv (folder + example JSON adapter), notifications (tray)
  ui/                      theme, brand, icons, reusable_widgets, login_window, main_window and one module per page
templates/                 CSV templates, privacy notice template
tests/                     pytest suite (services, security, imports, backup, privacy, UI smoke test)
```

## Database (SQLite)
| Table | Purpose |
|---|---|
| app_settings | key/value settings (JSON) |
| staff_users | accounts, role, scrypt hash, lock-out |
| customers | profile, loyalty ID (unique, Luhn check digit), phone (unique when set), tier cache, override |
| products | SKU (unique), price, tax override, stock |
| sales / sale_items | receipts (unique number), totals, link method, status; frozen item prices and tax |
| refunds / refund_items | per-item refunds with exact amounts |
| customer_visits | check-ins and purchases (retention applies) |
| alerts | returning-customer alerts, status, OS notification result |
| consent_records | consent history (data, marketing, biometric) |
| vip_tiers | editable tier rules |
| import_jobs | import results and row errors |
| audit_log | append-only (triggers block UPDATE/DELETE) |

Rules enforced by the database: foreign keys, unique receipt numbers, non-negative money, sales cannot be deleted
(except demo records), audit log append-only. Money is stored as integers.

## Flow of a sale
POS screen -> `SalesService.quote()` (prices from the catalogue) -> `checkout()` in one transaction:
stock check, receipt number, sale + items, stock update, visit -> audit -> `VipService.recalculate()`.

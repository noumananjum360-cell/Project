# NomLoyal - Retail CRM & Loyalty (Devnom)

A Windows desktop app for clothing, saree, jewellery, shoe, cosmetics and electronics shops:
customer CRM, POS billing, refunds, automatic VIP tiers, returning-customer alerts, analytics,
CSV/POS imports, staff roles, audit log, backups and privacy tools. Fully offline; SQLite database.

Same look and structure as FabriScan (sidebar, cards, calm tables), with its own palette:
deep teal + VIP gold on a cool off-white, dark-navy text, light and dark themes.

> **No face recognition is included.** Customers are identified by loyalty ID, QR card, phone number
> or cashier selection. A camera preview and a documented recognition-provider interface are included;
> recognition is off by default and can only be enabled with a real, validated provider and explicit
> customer consent (see `docs/RECOGNITION_PROVIDERS.md`).

## Quick start

**Use the program (Windows)**
1. Install **Python 3.12** (or 3.11) from python.org - tick *Add python.exe to PATH*.
2. Double-click **`build.bat`**. It creates `.venv`, installs pinned packages, runs the tests, builds the
   app and tests the built program. It stays open and explains what to do if anything fails.
3. Your app: **`dist\NomLoyal\NomLoyal.exe`**. Copy the whole `dist\NomLoyal` folder to the shop PC.
4. First start shows the **Welcome** screen: store details + the Admin account (there are no default
   passwords). Tick *Load sample data* to try the app with clearly-labelled demo records.

**Development mode**
```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python main.py            # run the app
.venv\Scripts\python -m pytest          # run the tests
.venv\Scripts\python main.py --selftest # quick end-to-end check
```
or double-click `Run NomLoyal (dev).bat` after running `build.bat` once.

Optional single-file exe: `build_onefile.bat` -> `dist\NomLoyal-portable.exe` (starts slower).

## Where things are stored
| What | Where |
|---|---|
| Database (customers, sales, settings) | `%LOCALAPPDATA%\Devnom\NomLoyal\nomloyal.db` |
| Backups | `%LOCALAPPDATA%\Devnom\NomLoyal\backups\` |
| Exports (CSV, PDF receipts, customer data) | `%LOCALAPPDATA%\Devnom\NomLoyal\exports\` |
| Logs | `%LOCALAPPDATA%\Devnom\NomLoyal\logs\nomloyal.log` |

Building or updating the program never touches this folder. Set `NOMLOYAL_HOME` to use another folder.

## Main features
- **POS billing** - barcode/SKU search, multi-item bills, line and bill discounts (amount or %), configurable tax
  (store default + per product), payment methods, receipt preview/print/PDF. Totals are always calculated by the
  sales service from catalogue prices; the screen cannot set a total. Cashier discount limit.
- **Customer link only with evidence** - loyalty ID, QR loyalty card, phone number or cashier selection.
  Walk-in sales are allowed and can be linked later (verified only).
- **Refunds & voids** - per-item quantity refunds (exact share of what was paid, last unit gets the remainder),
  optional restock, statuses completed / partially refunded / refunded / voided. Sales can never be deleted.
- **VIP engine** - Bronze, Silver, Gold, VIP (editable, add your own). Rule A: single purchase >= PKR 50,000.
  Rule B: net spending >= PKR 100,000 in 12 months. Refunds subtract, voids never count. Recalculated after every
  sale, refund, void, import or rule change. Shows the reasons and the qualifying receipts. Audited manual overrides.
- **Returning-customer alerts** - front-desk check-in by QR / loyalty ID / phone; managers are alerted; duplicate
  prevention; acknowledge / dismiss; history. Windows notifications show only a generic message (no names or
  purchases). Demo/simulated alerts are labelled.
- **Customer CRM** - profiles, tags, notes, consent history, purchase timeline, lifetime net spending, average
  transaction, favourite categories, refunds, VIP reasons, archive, export, delete/anonymise.
- **Analytics** - daily/monthly sales, by product and category, top sellers, repeat customers, VIP list, lifetime
  value, refunds, retention, CSV export (permission checked).
- **Import & POS** - CSV import with preview, row-level errors, duplicate detection and total reconciliation for
  customers, products and sales; templates; exports; a CSV-folder connector and an example JSON adapter.
- **Staff & security** - Admin / Manager / Cashier, scrypt password hashing, lock-out after 5 failures, auto-lock,
  forced password change after a reset, append-only audit log.
- **Backup & restore** - validated backups, safety copy before restore, schema migrations.
- **Privacy** - consent records and withdrawal, data export, correction, deletion/anonymisation, retention rules,
  editable privacy notice, operator checklist.

## Roles
| | Admin | Manager | Cashier |
|---|---|---|---|
| Sell, look up / register customers | yes | yes | yes |
| Purchase history, spending, emails, notes in full | yes | yes | service info only |
| Refunds, voids, VIP overrides, alerts, imports, reports | yes | yes | - |
| VIP rules | yes | if allowed in Store settings | - |
| Staff, settings, privacy, backups, audit log, customer export/delete | yes | - | - |

## Documentation
- `docs/ARCHITECTURE.md` - folders, database design, how the pieces fit
- `docs/TROUBLESHOOTING.md` - build and runtime problems
- `docs/SECURITY_PRIVACY.md` - security notes, privacy checklist, backups
- `docs/POS_CONNECTOR_GUIDE.md` - adding a vendor POS connector
- `docs/RECOGNITION_PROVIDERS.md` - rules for any future recognition provider
- `docs/STATUS.md` - implemented / partial / not implemented

## Name
**NomLoyal** follows the Devnom "Nom" family (NomLoad, NomFabric). Other options if you prefer:
NomClient, NomVIP, NomShop, NomRetail.

## Screenshots
`docs/screenshots/` - login, dashboard (light and dark), POS billing, customers, customer profile and VIP
reasons, VIP list, alerts, sales, receipt, analytics, import, camera and privacy pages (taken from the real app
with demo data).

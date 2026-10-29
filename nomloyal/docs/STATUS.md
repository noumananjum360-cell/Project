# Status (version 1.0.0)

## Implemented and tested
- Welcome/first-run setup, login, lock-out, auto-lock, password change/reset, roles and permissions
- Customer CRM (create, edit, search, filters, pagination, archive, tags, notes, consent history, timeline,
  lifetime net spending, average transaction, favourite categories, VIP reasons, export, delete/anonymise)
- Loyalty ID with check digit, QR loyalty card (display and print), lookup by loyalty ID / QR / phone / selection
- Products with categories, tax override and stock; stock adjustments
- POS billing with discounts, tax, payment methods, receipt preview/print/PDF, cashier discount limit
- Refunds (per item and quantity, restock), voids, transaction history and filters, linking walk-in sales
- VIP engine (Rules A and B, editable tiers, windows, refunds subtract, voids excluded, overrides, recalculation)
- Returning-customer alerts with duplicate prevention, acknowledge/dismiss, history, privacy-safe tray notifications
- Dashboard and analytics (daily/monthly, product, category, top sellers, repeat, VIP, lifetime value, refunds,
  retention), CSV export with permission checks
- CSV import with preview, validation, duplicates, reconciliation; templates; exports; import history
- POS connectors: CSV folder, example JSON adapter
- Backup, validation and restore with safety copy; migrations
- Privacy: consent, withdrawal, retention rules, privacy notice editor, operator checklist
- Camera: USB/RTSP connection test, discovery, live preview with active indicator, reconnection
- Demo data (labelled, removable), light/dark theme, 1366x768 layout
- 55 automated tests; `main.py --selftest`; PyInstaller folder build verified (on Linux)

## Partially implemented
- Windows build: `build.bat` and the spec are complete; the final .exe must be built on Windows (the folder build
  and its self-test were verified on Linux).
- Printing: uses the Windows printer dialog; thermal-printer specific formatting (paper cut, cash drawer) is not included.

## Not implemented (by design or out of scope)
- Biometric / face recognition: only the provider interface and settings exist; no engine is bundled.
- Direct integrations with named POS vendors (connector guide provided).
- Online/cloud sync, multi-branch, e-mail/SMS marketing, subscription billing/licensing module.

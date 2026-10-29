# Adding a POS connector

NomLoyal is not integrated with any specific POS brand. Two working connectors are included:
- **CSV folder** - point it at the folder where your POS saves sales CSV files (template: `templates/sales_template.csv`).
  Imported files are moved to `imported/` so they are never imported twice.
- **Example JSON adapter** (`app/integrations/pos_csv.py`) - shows how to map another system's export.

## Write your own
1. Subclass `app.integrations.pos_base.POSConnector`.
2. `test_connection()` returns `(ok, message)` and must not change data.
3. `fetch_sales_rows()` returns one dict per sold item with the sales template keys:
   `receipt_no, sold_at (YYYY-MM-DD HH:MM), customer_loyalty_id, customer_phone, sku, qty, unit_price,
   line_discount, payment_method, reported_total`.
4. Pass the rows to `ImportService.preview("sales", source_name, rows)` and, after the user has seen the
   preview, `ImportService.commit(preview)`. You get validation, duplicate detection (receipt number),
   reconciliation against `reported_total`, customer linking by exact loyalty ID / phone only, audit and VIP
   recalculation for free.
5. Add tests with a recorded sample export. Only describe the connector as "integrated" after testing it against
   the vendor's real system.

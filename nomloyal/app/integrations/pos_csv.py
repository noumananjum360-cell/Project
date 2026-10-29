"""Working connectors:

* CsvFolderConnector - any POS that can export sales to CSV files in a folder (many can). Files already
  imported are moved to an 'imported' sub-folder so they are never imported twice.
* ExampleJsonPOSAdapter - a documented example of a vendor adapter. It maps a simple JSON export
  ({"receipts": [{"number", "date", "customer": {"loyalty_id", "phone"}, "payment", "total",
  "lines": [{"sku", "qty", "price", "discount"}]}]}) to NomLoyal rows. It is an EXAMPLE format,
  not a specific vendor integration.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.integrations.pos_base import POSConnector
from app.services.import_service import read_csv


class CsvFolderConnector(POSConnector):
    name = "CSV folder"
    description = "Imports sales CSV files that your POS exports into a folder."

    def __init__(self, folder: str | Path):
        self.folder = Path(folder) if folder else None

    def test_connection(self) -> tuple[bool, str]:
        if not self.folder or not self.folder.is_dir():
            return False, "Choose an existing folder."
        n = len(self.pending_files())
        return True, f"Folder found - {n} CSV file(s) waiting."

    def pending_files(self) -> list[Path]:
        return sorted(self.folder.glob("*.csv")) if self.folder and self.folder.is_dir() else []

    def fetch_sales_rows(self) -> list[dict]:
        rows = []
        for f in self.pending_files():
            rows += read_csv(f)
        return rows

    def mark_imported(self):
        done = self.folder / "imported"
        done.mkdir(exist_ok=True)
        for f in self.pending_files():
            shutil.move(str(f), done / f.name)


class ExampleJsonPOSAdapter(POSConnector):
    name = "Example JSON POS"
    description = "Example adapter for a JSON receipt export (template for a vendor-specific connector)."

    def __init__(self, path: str | Path):
        self.path = Path(path) if path else None

    def test_connection(self) -> tuple[bool, str]:
        if not self.path or not self.path.is_file():
            return False, "Choose the JSON export file."
        try:
            n = len(json.loads(self.path.read_text(encoding="utf-8")).get("receipts", []))
        except (ValueError, AttributeError) as exc:
            return False, f"Not a valid export: {exc}"
        return True, f"{n} receipt(s) found."

    def fetch_sales_rows(self) -> list[dict]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = []
        for r in data.get("receipts", []):
            cust = r.get("customer") or {}
            for ln in r.get("lines", []):
                rows.append({"receipt_no": str(r["number"]), "sold_at": r["date"],
                             "customer_loyalty_id": cust.get("loyalty_id", ""), "customer_phone": cust.get("phone", ""),
                             "sku": ln["sku"], "qty": str(ln["qty"]), "unit_price": str(ln["price"]),
                             "line_discount": str(ln.get("discount", 0)), "payment_method": r.get("payment", "Cash"),
                             "reported_total": str(r.get("total", ""))})
        return rows

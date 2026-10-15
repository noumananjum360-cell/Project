"""Products (profiles), gate passes and gate pass import / ERP connectors."""
from __future__ import annotations

import abc
import csv
import time
from dataclasses import dataclass, field
from pathlib import Path

from nomload.data import crypto
from nomload.data.db import Database
from nomload.services.context import User, audit


# ----------------------------------------------------------------- products
@dataclass
class Product:
    id: int
    name: str
    sku: str
    detector_class: str
    units_per_detection: int
    tolerance_units: int | None
    tolerance_pct: float | None
    active: bool
    notes: str


class ProductService:
    def __init__(self, db: Database):
        self.db = db

    def _row(self, r) -> Product:
        return Product(r["id"], r["name"], r["sku"], r["detector_class"], r["units_per_detection"],
                       r["tolerance_units"], r["tolerance_pct"], bool(r["active"]), r["notes"])

    def list(self, active_only=False) -> list[Product]:
        sql = "SELECT * FROM products" + (" WHERE active=1" if active_only else "") + " ORDER BY name"
        return [self._row(r) for r in self.db.q(sql)]

    def get(self, pid: int) -> Product | None:
        r = self.db.one("SELECT * FROM products WHERE id=?", (pid,))
        return self._row(r) if r else None

    def by_name(self, name: str) -> Product | None:
        r = self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE OR (sku<>'' AND sku=? COLLATE NOCASE)",
                        (name.strip(), name.strip()))
        return self._row(r) if r else None

    def save(self, actor: User, name: str, detector_class: str, units_per_detection: int = 1, sku: str = "",
             tolerance_units=None, tolerance_pct=None, notes: str = "", pid: int | None = None, active: bool = True) -> int:
        if units_per_detection < 1:
            raise ValueError("Units per detection must be at least 1")
        if pid:
            self.db.execute("UPDATE products SET name=?, sku=?, detector_class=?, units_per_detection=?, tolerance_units=?, "
                            "tolerance_pct=?, notes=?, active=? WHERE id=?",
                            (name, sku, detector_class, units_per_detection, tolerance_units, tolerance_pct, notes,
                             int(active), pid))
            audit(self.db, actor, "product_updated", "product", pid, {"name": name, "class": detector_class,
                                                                      "units": units_per_detection})
            return pid
        pid = self.db.execute("INSERT INTO products(name, sku, detector_class, units_per_detection, tolerance_units, "
                              "tolerance_pct, notes, active, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                              (name, sku, detector_class, units_per_detection, tolerance_units, tolerance_pct, notes,
                               int(active), time.time()))
        audit(self.db, actor, "product_created", "product", pid, {"name": name})
        return pid

    def add_sample(self, pid: int, path: str):
        self.db.execute("INSERT INTO product_samples(product_id, path, created_at) VALUES (?,?,?)", (pid, path, time.time()))

    def samples(self, pid: int) -> list[str]:
        return [r["path"] for r in self.db.q("SELECT path FROM product_samples WHERE product_id=? ORDER BY id DESC", (pid,))]

    def ensure_defaults(self):
        if self.db.scalar("SELECT COUNT(*) FROM products"):
            return
        from nomload.services.context import SYSTEM
        defaults = [("Cement 50kg bag", "bag", 1), ("Flour 50kg bag", "bag", 1), ("Urea 50kg bag", "bag", 1),
                    ("Sugar 50kg bag", "bag", 1), ("Rice 25kg bag", "bag", 1), ("Carton 1.5L x6", "carton", 1),
                    ("Beverage crate x24", "crate", 1), ("Shrink pack 500ml x12", "pack", 1)]
        for name, cls, u in defaults:
            self.save(SYSTEM, name, cls, u)


# ----------------------------------------------------------------- gate passes
@dataclass
class GatePassItem:
    product_id: int
    product_name: str
    expected_qty: int


@dataclass
class GatePass:
    id: int
    number: str
    vehicle_no: str
    customer: str
    driver_name: str
    driver_phone: str
    destination: str
    status: str
    source: str
    notes: str
    created_at: float
    items: list[GatePassItem] = field(default_factory=list)

    @property
    def total_expected(self) -> int:
        return sum(i.expected_qty for i in self.items)


class GatePassService:
    def __init__(self, db: Database, products: ProductService):
        self.db = db
        self.products = products

    def get(self, gid: int) -> GatePass | None:
        r = self.db.one("SELECT * FROM gate_passes WHERE id=?", (gid,))
        if r is None:
            return None
        items = [GatePassItem(i["product_id"], i["name"], i["expected_qty"]) for i in self.db.q(
            "SELECT g.product_id, g.expected_qty, p.name FROM gate_pass_items g JOIN products p ON p.id=g.product_id "
            "WHERE g.gate_pass_id=? ORDER BY g.id", (gid,))]
        return GatePass(r["id"], r["number"], r["vehicle_no"], r["customer"], r["driver_name"],
                        crypto.decrypt(r["driver_phone"]) or "", r["destination"], r["status"], r["source"],
                        r["notes"], r["created_at"], items)

    def by_number(self, number: str) -> GatePass | None:
        r = self.db.one("SELECT id FROM gate_passes WHERE number=? COLLATE NOCASE", (number.strip(),))
        return self.get(r["id"]) if r else None

    def list(self, status: tuple = ("open", "loading"), search: str = "", limit: int = 300) -> list[GatePass]:
        sql = "SELECT id FROM gate_passes WHERE 1=1"
        args: list = []
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            args += list(status)
        if search:
            sql += " AND (number LIKE ? OR vehicle_no LIKE ? OR customer LIKE ?)"
            args += [f"%{search}%"] * 3
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [self.get(r["id"]) for r in self.db.q(sql, args)]

    def create(self, actor: User, number: str, items: list[tuple[int, int]], vehicle_no: str = "", customer: str = "",
               driver_name: str = "", driver_phone: str = "", destination: str = "", notes: str = "",
               source: str = "manual") -> int:
        number = number.strip()
        if not number:
            raise ValueError("Gate pass number is required")
        if not items:
            raise ValueError("Add at least one product")
        if self.by_number(number):
            raise ValueError(f"Gate pass {number} already exists")
        with self.db.tx() as c:
            gid = c.execute("INSERT INTO gate_passes(number, vehicle_no, customer, driver_name, driver_phone, destination, "
                            "status, source, notes, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (number, vehicle_no.strip().upper(), customer.strip(), driver_name.strip(),
                             crypto.encrypt(driver_phone.strip()) or "", destination.strip(), "open", source, notes,
                             actor.id or None, time.time())).lastrowid
            for pid, qty in items:
                c.execute("INSERT INTO gate_pass_items(gate_pass_id, product_id, expected_qty) VALUES (?,?,?)",
                          (gid, pid, int(qty)))
        audit(self.db, actor, "gate_pass_created", "gate_pass", gid, {"number": number, "source": source,
                                                                      "items": items})
        return gid

    def update_items(self, actor: User, gid: int, items: list[tuple[int, int]], vehicle_no: str | None = None):
        with self.db.tx() as c:
            c.execute("DELETE FROM gate_pass_items WHERE gate_pass_id=?", (gid,))
            for pid, qty in items:
                c.execute("INSERT INTO gate_pass_items(gate_pass_id, product_id, expected_qty) VALUES (?,?,?)",
                          (gid, pid, int(qty)))
            if vehicle_no is not None:
                c.execute("UPDATE gate_passes SET vehicle_no=? WHERE id=?", (vehicle_no.strip().upper(), gid))
        audit(self.db, actor, "gate_pass_edited", "gate_pass", gid, {"items": items, "vehicle_no": vehicle_no})

    def set_status(self, gid: int, status: str, actor: User | None = None):
        self.db.execute("UPDATE gate_passes SET status=? WHERE id=?", (status, gid))
        audit(self.db, actor, "gate_pass_status", "gate_pass", gid, status)

    def match_plate(self, plate: str) -> GatePass | None:
        """Find an open gate pass whose vehicle number matches a read plate."""
        from nomload.core.plate_formats import edit_distance, plates_match
        best, best_d = None, 99
        for gp in self.list(("open",)):
            if gp.vehicle_no and plates_match(gp.vehicle_no, plate, 1):
                d = edit_distance(gp.vehicle_no, plate)
                if d < best_d:
                    best, best_d = gp, d
        return best

    # ------------------------------------------------------------- import
    def import_rows(self, actor: User, rows: list[dict], source: str = "csv") -> tuple[int, list[str]]:
        """Rows: gate_pass, vehicle, customer, driver, phone, destination, product, quantity.

        Multiple rows with the same gate_pass number become one gate pass with
        several products. Unknown products are reported, not created silently.
        """
        groups: dict[str, dict] = {}
        errors = []
        for n, r in enumerate(rows, start=2):
            r = {_norm_key(k): (str(v).strip() if v is not None else "") for k, v in r.items() if k}
            num = r.get("gate_pass") or r.get("gatepass") or r.get("number") or r.get("invoice")
            prod = r.get("product") or r.get("item") or r.get("sku")
            qty = r.get("quantity") or r.get("qty") or r.get("expected")
            if not num or not prod or not qty:
                errors.append(f"Row {n}: gate pass number, product and quantity are required")
                continue
            p = self.products.by_name(prod)
            if p is None:
                errors.append(f"Row {n}: unknown product '{prod}' (add it under Products first)")
                continue
            try:
                q = int(float(qty))
            except ValueError:
                errors.append(f"Row {n}: invalid quantity '{qty}'")
                continue
            g = groups.setdefault(num, {"vehicle_no": r.get("vehicle") or r.get("vehicle_no") or r.get("truck", ""),
                                        "customer": r.get("customer") or r.get("distributor", ""),
                                        "driver_name": r.get("driver", ""), "driver_phone": r.get("phone", ""),
                                        "destination": r.get("destination", ""), "items": {}})
            g["items"][p.id] = g["items"].get(p.id, 0) + q
        created = 0
        for num, g in groups.items():
            try:
                self.create(actor, num, list(g["items"].items()), g["vehicle_no"], g["customer"], g["driver_name"],
                            g["driver_phone"], g["destination"], source=source)
                created += 1
            except ValueError as e:
                errors.append(f"{num}: {e}")
        return created, errors

    def import_file(self, actor: User, path: str | Path) -> tuple[int, list[str]]:
        path = Path(path)
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            it = ws.iter_rows(values_only=True)
            header = [str(h or "") for h in next(it)]
            rows = [dict(zip(header, row)) for row in it if any(v is not None for v in row)]
            return self.import_rows(actor, rows, "excel")
        with open(path, newline="", encoding="utf-8-sig") as f:
            return self.import_rows(actor, list(csv.DictReader(f)), "csv")


def _norm_key(k: str) -> str:
    return str(k).strip().lower().replace(" ", "_").replace("-", "_").replace(".", "")


TEMPLATE_HEADER = ["gate_pass", "vehicle", "customer", "driver", "phone", "destination", "product", "quantity"]


def write_import_template(path: str | Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(TEMPLATE_HEADER)
        w.writerow(["GP-1001", "LES-4721", "Al-Madina Traders", "Aslam", "0300-1234567", "Multan", "Flour 50kg bag", 400])
        w.writerow(["GP-1001", "LES-4721", "Al-Madina Traders", "Aslam", "0300-1234567", "Multan", "Sugar 50kg bag", 100])
        w.writerow(["GP-1002", "TLA-552", "City Distributors", "Rafiq", "", "Hyderabad", "Carton 1.5L x6", 600])


# ----------------------------------------------------------------- ERP connector interface
class ERPConnector(abc.ABC):
    """Interface for pulling gate passes from an ERP (SAP B1, Odoo, Oracle, custom).

    Implement ``fetch_open_gate_passes`` returning rows in the import format
    (see TEMPLATE_HEADER) and optionally ``push_result`` to post the counted
    quantities back. Register the class in ``CONNECTORS``; it then appears in
    Settings and is polled by ``sync_from_erp``.
    """
    name = "base"

    def __init__(self, config: dict):
        self.config = config

    @abc.abstractmethod
    def fetch_open_gate_passes(self) -> list[dict]:
        ...

    def push_result(self, gate_pass_number: str, result: dict) -> None:  # pragma: no cover - optional
        return None


class FolderDropConnector(ERPConnector):
    """Picks up CSV/XLSX files that an ERP exports into a shared folder."""
    name = "folder"

    def fetch_open_gate_passes(self) -> list[dict]:
        folder = Path(self.config.get("folder", ""))
        rows: list[dict] = []
        if not folder.is_dir():
            return rows
        for p in sorted(folder.glob("*.csv")):
            with open(p, newline="", encoding="utf-8-sig") as f:
                rows += list(csv.DictReader(f))
            p.rename(p.with_suffix(".imported"))
        return rows


CONNECTORS: dict[str, type[ERPConnector]] = {"folder": FolderDropConnector}


def sync_from_erp(gps: GatePassService, actor: User, connector: ERPConnector) -> tuple[int, list[str]]:
    return gps.import_rows(actor, connector.fetch_open_gate_passes(), source=f"erp:{connector.name}")

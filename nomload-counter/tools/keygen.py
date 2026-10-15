"""NomLoad Counter - vendor licence key tool (Devnom internal, never ship to customers).

  python tools/keygen.py init                      # create vendor key pair (once)
  python tools/keygen.py batch --tier professional --count 50 [--expiry 2027-12-31] [--start-id 1000] --out keys.csv
  python tools/keygen.py activation --request-code ABCDE-FGHIJ-KLMNO --tier starter --key-id 1234
  python tools/keygen.py revoke --ids 1001 1002 --out revoked.nlr
  python tools/keygen.py verify NLC-XXXXXX-...
  python tools/keygen.py gui                       # simple window for the sales team

The private key lives in tools/vendor_keys/vendor_private.pem (git-ignored).
Back it up safely: if it is lost, no new keys can be generated for existing builds.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from nomload.licensing.license import (TIER_BY_NAME, TIERS, decode_key, load_public_key, make_key,  # noqa: E402
                                       make_revocation, parse_request_code, public_key_path)

KEY_DIR = Path(__file__).resolve().parent / "vendor_keys"
PRIV = KEY_DIR / "vendor_private.pem"


def load_private() -> Ed25519PrivateKey:
    if not PRIV.exists():
        sys.exit("No vendor key. Run:  python tools/keygen.py init")
    return serialization.load_pem_private_key(PRIV.read_bytes(), password=None)


def cmd_init(a):
    if PRIV.exists() and not a.force:
        sys.exit(f"{PRIV} already exists (use --force to replace - old keys will stop working!)")
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    k = Ed25519PrivateKey.generate()
    PRIV.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    (KEY_DIR / "vendor_public.pem").write_bytes(pub)
    public_key_path().write_bytes(pub)
    print(f"Created {PRIV}\nInstalled public key into {public_key_path()} - rebuild the app.")


def _tier(name: str) -> int:
    t = TIER_BY_NAME.get(name.lower())
    if not t:
        sys.exit(f"unknown tier {name}; use starter/professional/enterprise")
    return t


def _expiry(s: str | None):
    return dt.date.fromisoformat(s) if s else None


def generate_batch(priv, tier: int, count: int, start_id: int | None, expiry, bays: int | None) -> list[dict]:
    start = start_id if start_id is not None else secrets.randbelow(2 ** 31)
    rows = []
    for i in range(count):
        kid = (start + i) % 2 ** 32
        rows.append({"key_id": kid, "tier": TIERS[tier][0], "max_bays": bays or TIERS[tier][1],
                     "expiry": expiry.isoformat() if expiry else "perpetual",
                     "key": make_key(priv, tier, kid, bays, expiry), "customer": "", "issued": dt.date.today().isoformat()})
    return rows


def cmd_batch(a):
    rows = generate_batch(load_private(), _tier(a.tier), a.count, a.start_id, _expiry(a.expiry), a.bays)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} keys to {a.out}")


def cmd_activation(a):
    fp = parse_request_code(a.request_code)
    key = make_key(load_private(), _tier(a.tier), a.key_id, a.bays, _expiry(a.expiry), fp[:8])
    print(key)


def cmd_revoke(a):
    Path(a.out).write_bytes(make_revocation(load_private(), a.ids))
    print(f"Wrote revocation list with {len(a.ids)} key id(s) to {a.out}")


def cmd_verify(a):
    pub = load_public_key(KEY_DIR / "vendor_public.pem") or load_public_key()
    info = decode_key(a.key, pub)
    print(f"Valid key: id={info.key_id} tier={info.tier_name} bays={info.max_bays} "
          f"expiry={info.expiry or 'perpetual'} machine_locked={info.machine_locked}")


def cmd_gui(a):
    import os
    from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QFileDialog, QFormLayout, QMessageBox,
                                   QPushButton, QSpinBox, QCheckBox, QWidget, QPlainTextEdit, QLineEdit)
    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("NomLoad Licence Key Generator (Devnom)")
    f = QFormLayout(w)
    tier = QComboBox(); tier.addItems(["Starter", "Professional", "Enterprise"])
    count = QSpinBox(); count.setRange(1, 10000); count.setValue(10)
    has_exp = QCheckBox("Expires")
    exp = QDateEdit(); exp.setCalendarPopup(True); exp.setDate(dt.date.today() + dt.timedelta(days=365))
    req = QLineEdit(); req.setPlaceholderText("Customer request code (for machine-locked activation key)")
    out = QPlainTextEdit(); out.setReadOnly(True)
    f.addRow("Tier", tier); f.addRow("Number of keys", count); f.addRow(has_exp, exp); f.addRow("Request code", req)
    gen = QPushButton("Generate"); save = QPushButton("Save CSV...")
    f.addRow(gen, save); f.addRow(out)
    state = {"rows": []}

    def do_gen():
        priv = load_private()
        t = tier.currentIndex() + 1
        e = exp.date().toPython() if has_exp.isChecked() else None
        if req.text().strip():
            key = make_key(priv, t, secrets.randbelow(2 ** 31), None, e, parse_request_code(req.text())[:8])
            state["rows"] = [{"key": key, "tier": TIERS[t][0], "request_code": req.text().strip()}]
        else:
            state["rows"] = generate_batch(priv, t, count.value(), None, e, None)
        out.setPlainText("\n".join(r["key"] for r in state["rows"]))

    def do_save():
        if not state["rows"]:
            return
        p, _ = QFileDialog.getSaveFileName(w, "Save keys", os.path.expanduser("~/nomload_keys.csv"), "CSV (*.csv)")
        if p:
            with open(p, "w", newline="", encoding="utf-8") as fh:
                wr = csv.DictWriter(fh, fieldnames=list(state["rows"][0].keys()))
                wr.writeheader(); wr.writerows(state["rows"])
            QMessageBox.information(w, "Saved", f"Saved {len(state['rows'])} keys")

    gen.clicked.connect(do_gen); save.clicked.connect(do_save)
    w.resize(760, 520); w.show()
    sys.exit(app.exec())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("batch"); p.add_argument("--tier", required=True); p.add_argument("--count", type=int, default=10)
    p.add_argument("--start-id", type=int); p.add_argument("--expiry"); p.add_argument("--bays", type=int)
    p.add_argument("--out", default="keys.csv"); p.set_defaults(fn=cmd_batch)
    p = sub.add_parser("activation"); p.add_argument("--request-code", required=True); p.add_argument("--tier", required=True)
    p.add_argument("--key-id", type=int, default=secrets.randbelow(2 ** 31)); p.add_argument("--expiry")
    p.add_argument("--bays", type=int); p.set_defaults(fn=cmd_activation)
    p = sub.add_parser("revoke"); p.add_argument("--ids", type=int, nargs="+", required=True)
    p.add_argument("--out", default="revoked.nlr"); p.set_defaults(fn=cmd_revoke)
    p = sub.add_parser("verify"); p.add_argument("key"); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("gui"); p.set_defaults(fn=cmd_gui)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

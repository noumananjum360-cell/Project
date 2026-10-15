"""Offline licensing for NomLoad Counter.

Keys are signed by the vendor with Ed25519; the app only holds the public key,
so keys cannot be forged by inspecting the program.

Key payload (10 bytes, packed, then signed, then Base32 encoded as ``NLC-XXXXXX-...``):
    version u8 | tier u8 | max_bays u8 (255 = unlimited) | flags u8 |
    expiry u16 (days since 2024-01-01, 0 = perpetual) | key_id u32 |
    [fingerprint 8 bytes when flags & MACHINE_LOCKED]

* Product key (not machine locked): on first activation the key is bound to
  this PC's hardware fingerprint. The binding file is HMAC-protected with the
  fingerprint, so copying the installation to another PC invalidates it.
* Activation key (machine locked): issued by the vendor for a specific
  *request code* (the PC fingerprint) - used for re-activation after a PC
  replacement or for strict deployments. The signed fingerprint must match.
* Revocation: key IDs in the built-in list or in a vendor-signed ``.nlr``
  revocation file imported by the customer are rejected.
* Trial: 14 days from first run with 2 bays, reports watermarked "TRIAL".
  The first-run date is stored in several places and clock roll-back is
  detected.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import platform
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

EPOCH = dt.date(2024, 1, 1)
MACHINE_LOCKED = 0x01
TIERS = {1: ("Starter", 1), 2: ("Professional", 4), 3: ("Enterprise", 255)}
TIER_BY_NAME = {"starter": 1, "professional": 2, "pro": 2, "enterprise": 3}
TRIAL_DAYS = 14
TRIAL_BAYS = 2
BUILTIN_REVOKED: set[int] = set()   # vendor adds leaked key ids here in new releases
_APP_SALT = b"NomLoad-Counter/Devnom/licence/v1"
_FMT = ">BBBBHI"
_PLEN = struct.calcsize(_FMT)  # 10 bytes


def public_key_path() -> Path:
    return Path(__file__).resolve().parent / "vendor_public_key.pem"


def load_public_key(path: Path | None = None) -> Ed25519PublicKey | None:
    p = path or public_key_path()
    if not p.exists():
        return None
    return serialization.load_pem_public_key(p.read_bytes())


# ----------------------------------------------------------------- fingerprint
def _win_machine_guid() -> str:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                           winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        return winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception:
        return ""


def _win_volume_serial() -> str:
    try:
        import ctypes
        serial = ctypes.c_uint32()
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        ctypes.windll.kernel32.GetVolumeInformationW(drive, None, 0, ctypes.byref(serial), None, None, None, 0)
        return f"{serial.value:08X}"
    except Exception:
        return ""


def _win_board_serial() -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_BaseBoard).SerialNumber"], capture_output=True, text=True,
                             timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout.strip()
    except Exception:
        return ""


def hardware_fingerprint() -> bytes:
    """Stable 16-byte machine fingerprint."""
    override = os.environ.get("NOMLOAD_FINGERPRINT")  # tests
    if override:
        return hashlib.sha256(override.encode()).digest()[:16]
    parts = []
    if sys.platform == "win32":
        parts += [_win_machine_guid(), _win_volume_serial(), _win_board_serial(),
                  os.environ.get("PROCESSOR_IDENTIFIER", "")]
    else:
        for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                parts.append(Path(f).read_text().strip())
                break
            except OSError:
                pass
        parts.append(platform.machine())
    parts.append(platform.node() if not any(parts[:1]) else "")
    return hashlib.sha256("|".join(parts).encode()).digest()[:16]


def _b32(b: bytes) -> str:
    return base64.b32encode(b).decode().rstrip("=")


def _unb32(s: str) -> bytes:
    s = s.upper().replace("-", "").replace(" ", "")
    s = s.replace("0", "O").replace("1", "I").replace("8", "B")  # tolerate typos
    return base64.b32decode(s + "=" * (-len(s) % 8))


def group(s: str, n: int = 6) -> str:
    return "-".join(s[i:i + n] for i in range(0, len(s), n))


def request_code(fp: bytes | None = None) -> str:
    """Code the customer sends to the vendor for a machine-locked activation key."""
    fp = fp or hardware_fingerprint()
    chk = hashlib.sha256(fp).digest()[:2]
    return group(_b32(fp[:8] + chk), 5)


def parse_request_code(code: str) -> bytes:
    raw = _unb32(code)
    fp8, chk = raw[:8], raw[8:10]
    if len(raw) < 10:
        raise ValueError("Request code is too short")
    return fp8 + chk


# ----------------------------------------------------------------- keys
@dataclass
class KeyInfo:
    version: int
    tier: int
    max_bays: int
    flags: int
    expiry: dt.date | None
    key_id: int
    fp8: bytes | None

    @property
    def tier_name(self) -> str:
        return TIERS.get(self.tier, ("Unknown", 0))[0]

    @property
    def machine_locked(self) -> bool:
        return bool(self.flags & MACHINE_LOCKED)


def make_key(private_key: Ed25519PrivateKey, tier: int, key_id: int, max_bays: int | None = None,
             expiry: dt.date | None = None, fp8: bytes | None = None) -> str:
    if max_bays is None:
        max_bays = TIERS[tier][1]
    flags = MACHINE_LOCKED if fp8 else 0
    exp = (expiry - EPOCH).days if expiry else 0
    payload = struct.pack(_FMT, 1, tier, min(255, max_bays), flags, exp, key_id)
    if fp8:
        payload += fp8[:8]
    sig = private_key.sign(payload)
    return "NLC-" + group(_b32(payload + sig))


def decode_key(key: str, public_key: Ed25519PublicKey) -> KeyInfo:
    k = key.strip().upper()
    if k.startswith("NLC-"):
        k = k[4:]
    try:
        raw = _unb32(k)
    except Exception:
        raise ValueError("This is not a valid NomLoad licence key.")
    if len(raw) < _PLEN + 64:
        raise ValueError("Licence key is incomplete.")
    flags = raw[3]
    plen = _PLEN + (8 if flags & MACHINE_LOCKED else 0)
    payload, sig = raw[:plen], raw[plen:plen + 64]
    try:
        public_key.verify(sig, payload)
    except InvalidSignature:
        raise ValueError("Licence key signature is invalid.")
    ver, tier, bays, flags, exp, kid = struct.unpack(_FMT, payload[:_PLEN])
    return KeyInfo(ver, tier, bays, flags, EPOCH + dt.timedelta(days=exp) if exp else None, kid,
                   payload[_PLEN:_PLEN + 8] if flags & MACHINE_LOCKED else None)


def make_revocation(private_key: Ed25519PrivateKey, key_ids: list[int]) -> bytes:
    body = json.dumps({"revoked": sorted(set(int(k) for k in key_ids)), "issued": time.time()}).encode()
    return json.dumps({"body": base64.b64encode(body).decode(),
                       "sig": base64.b64encode(private_key.sign(body)).decode()}).encode()


def read_revocation(data: bytes, public_key: Ed25519PublicKey) -> set[int]:
    obj = json.loads(data)
    body = base64.b64decode(obj["body"])
    public_key.verify(base64.b64decode(obj["sig"]), body)
    return set(json.loads(body)["revoked"])


# ----------------------------------------------------------------- status
@dataclass
class LicenseStatus:
    licensed: bool
    trial: bool
    expired: bool
    tier_name: str
    max_bays: int
    days_left: int | None
    message: str
    key_id: int | None = None

    @property
    def watermark(self) -> bool:
        return not self.licensed

    @property
    def usable(self) -> bool:
        return self.licensed or (self.trial and not self.expired)

    @property
    def label(self) -> str:
        if self.licensed:
            return f"{self.tier_name}: Licensed"
        if self.trial and not self.expired:
            return f"Trial: {self.days_left} day(s) left"
        return "Unlicensed"


class LicenseManager:
    def __init__(self, data_home: Path, db=None, public_key: Ed25519PublicKey | None = None):
        self.home = Path(data_home)
        self.db = db
        self.pub = public_key or load_public_key()
        self.file = self.home / "license.dat"
        self.revoked_file = self.home / "revoked.nlr"

    # ------------------------------------------------------------ binding
    def _mac(self, fp: bytes, body: bytes) -> str:
        return hmac.new(hashlib.sha256(_APP_SALT + fp).digest(), body, hashlib.sha256).hexdigest()

    def _read_binding(self) -> dict | None:
        if not self.file.exists():
            return None
        try:
            obj = json.loads(self.file.read_text())
            body = json.dumps(obj["data"], sort_keys=True).encode()
            if not hmac.compare_digest(obj["mac"], self._mac(hardware_fingerprint(), body)):
                return {"invalid": "This licence was activated on a different computer."}
            return obj["data"]
        except Exception:
            return {"invalid": "The licence file is damaged."}

    def _write_binding(self, data: dict):
        body = json.dumps(data, sort_keys=True).encode()
        self.file.write_text(json.dumps({"data": data, "mac": self._mac(hardware_fingerprint(), body)}))

    def revoked_ids(self) -> set[int]:
        ids = set(BUILTIN_REVOKED)
        if self.revoked_file.exists() and self.pub:
            try:
                ids |= read_revocation(self.revoked_file.read_bytes(), self.pub)
            except Exception:
                pass
        return ids

    def import_revocation(self, path: str | Path) -> int:
        if not self.pub:
            raise ValueError("No vendor public key installed.")
        data = Path(path).read_bytes()
        ids = read_revocation(data, self.pub)  # raises if forged
        self.revoked_file.write_bytes(data)
        return len(ids)

    # ------------------------------------------------------------ activation
    def activate(self, key: str) -> LicenseStatus:
        if not self.pub:
            raise ValueError("This build has no vendor public key; licence keys cannot be verified.")
        info = decode_key(key, self.pub)
        if info.key_id in self.revoked_ids():
            raise ValueError("This licence key has been revoked. Please contact Devnom.")
        if info.expiry and info.expiry < dt.date.today():
            raise ValueError("This licence key has expired.")
        fp = hardware_fingerprint()
        if info.machine_locked and info.fp8 != fp[:8]:
            raise ValueError("This activation key was issued for a different computer.")
        self._write_binding({"key": key.strip().upper(), "activated_at": time.time(), "fp": _b32(fp[:8])})
        return self.status()

    def deactivate(self):
        if self.file.exists():
            self.file.unlink()

    # ------------------------------------------------------------ trial
    def _trial_start(self) -> float:
        now = time.time()
        stamps = []
        marker = self.home / ".fr"
        if marker.exists():
            try:
                stamps.append(float(base64.b64decode(marker.read_text()).decode()))
            except Exception:
                pass
        if self.db is not None:
            v = self.db.scalar("SELECT value FROM meta WHERE key='created_at'")
            if v:
                stamps.append(float(v))
        if sys.platform == "win32":
            try:
                import winreg
                k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Devnom\NomLoad")
                try:
                    stamps.append(float(winreg.QueryValueEx(k, "fr")[0]))
                except OSError:
                    winreg.SetValueEx(k, "fr", 0, winreg.REG_SZ, str(now))
            except Exception:
                pass
        start = min(stamps) if stamps else now
        if not marker.exists():
            marker.write_text(base64.b64encode(str(start).encode()).decode())
        return start

    def _clock_ok(self) -> bool:
        f = self.home / ".ls"
        now = time.time()
        last = 0.0
        if f.exists():
            try:
                last = float(f.read_text())
            except ValueError:
                pass
        if now + 86400 < last:
            return False
        f.write_text(str(max(now, last)))
        return True

    # ------------------------------------------------------------ status
    def status(self) -> LicenseStatus:
        b = self._read_binding()
        if b and "invalid" not in b and self.pub:
            try:
                info = decode_key(b["key"], self.pub)
                if info.key_id in self.revoked_ids():
                    return LicenseStatus(False, False, True, info.tier_name, 0, None, "Licence key revoked", info.key_id)
                if info.expiry and info.expiry < dt.date.today():
                    return LicenseStatus(False, False, True, info.tier_name, 0, 0, "Licence expired", info.key_id)
                days = (info.expiry - dt.date.today()).days if info.expiry else None
                return LicenseStatus(True, False, False, info.tier_name, info.max_bays, days, "Licensed", info.key_id)
            except ValueError:
                pass
        clock_ok = self._clock_ok()
        start = self._trial_start()
        used = (time.time() - start) / 86400
        left = max(0, int(TRIAL_DAYS - used + 0.999))
        expired = left <= 0 or not clock_ok
        msg = "System clock was moved back" if not clock_ok else ("Trial expired" if expired else "Trial mode")
        if b and "invalid" in b:
            msg = b["invalid"]
        return LicenseStatus(False, True, expired, "Trial", TRIAL_BAYS if not expired else 0, left, msg)

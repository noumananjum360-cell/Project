"""Password hashing and field-level encryption.

* Passwords and supervisor PINs: scrypt with a random salt.
* Sensitive fields (RTSP credentials, SMTP/WhatsApp/SMS secrets, driver phone
  numbers): Fernet (AES-128-CBC + HMAC-SHA256). The data key is random per
  installation; on Windows it is additionally protected with DPAPI
  (machine scope), so copying the database to another PC does not reveal the
  secrets.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
_lock = threading.Lock()
_fernet: Fernet | None = None
_fernet_home: str | None = None


def hash_secret(secret: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(secret.encode("utf-8"), salt=salt, **_SCRYPT)
    return "scrypt${}${}${}${}${}".format(_SCRYPT["n"], _SCRYPT["r"], _SCRYPT["p"],
                                          base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def verify_secret(secret: str, stored: str | None) -> bool:
    if not stored or not secret:
        return False
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(secret.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r),
                              p=int(p), dklen=len(base64.b64decode(h)))
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


# ----------------------------------------------------------------- DPAPI (Windows)
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), buf)
    out = BLOB()
    CRYPTPROTECT_LOCAL_MACHINE = 0x4
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if protect:
        ok = fn(ctypes.byref(inp), "NomLoad", None, None, None, CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out))
    else:
        ok = fn(ctypes.byref(inp), None, None, None, None, CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out))
    if not ok:
        raise OSError("DPAPI call failed")
    res = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return res


def _key_file() -> Path:
    from nomload.config import data_home
    return data_home() / ".datakey"


def get_fernet() -> Fernet:
    global _fernet, _fernet_home
    from nomload.config import data_home
    home = str(data_home())
    with _lock:
        if _fernet is not None and _fernet_home == home:
            return _fernet
        kf = _key_file()
        if kf.exists():
            raw = kf.read_bytes()
            if raw.startswith(b"DPAPI:"):
                key = _dpapi(raw[6:], protect=False)
            else:
                key = raw.strip()
        else:
            key = Fernet.generate_key()
            if sys.platform == "win32":
                try:
                    kf.write_bytes(b"DPAPI:" + _dpapi(key, protect=True))
                except OSError:
                    kf.write_bytes(key)
            else:
                kf.write_bytes(key)
                os.chmod(kf, 0o600)
        _fernet = Fernet(key)
        _fernet_home = home
        return _fernet


def encrypt(text: str | None) -> str | None:
    if text is None or text == "":
        return text
    return "enc:" + get_fernet().encrypt(text.encode("utf-8")).decode()


def decrypt(token: str | None) -> str | None:
    if not token or not isinstance(token, str) or not token.startswith("enc:"):
        return token
    try:
        return get_fernet().decrypt(token[4:].encode()).decode("utf-8")
    except InvalidToken:
        return ""


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

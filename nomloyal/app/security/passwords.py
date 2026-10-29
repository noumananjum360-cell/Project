"""Password hashing with scrypt (Python standard library). Plain passwords are never stored or logged."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(base64.b64decode(dk)))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    """None when the password is acceptable, otherwise the reason."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password.isdigit() or password.isalpha():
        return "Use letters and numbers in the password."
    return None

"""Application context: settings, audit log, authentication and roles."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

from nomload.data import crypto
from nomload.data.db import Database

log = logging.getLogger(__name__)

# ----------------------------------------------------------------- roles
ROLES = ("admin", "supervisor", "clerk")
ROLE_LABELS = {"admin": "Admin", "supervisor": "Supervisor", "clerk": "Clerk"}
PERMISSIONS = {
    "run_sessions": {"admin", "supervisor", "clerk"},
    "view_history": {"admin", "supervisor", "clerk"},
    "view_reports": {"admin", "supervisor", "clerk"},
    "manage_gate_passes": {"admin", "supervisor", "clerk"},
    "approve_mismatch": {"admin", "supervisor"},
    "review_counts": {"admin", "supervisor"},
    "edit_counts": {"admin", "supervisor"},
    "manage_products": {"admin", "supervisor"},
    "manage_cameras": {"admin"},
    "manage_training": {"admin"},
    "manage_users": {"admin"},
    "manage_settings": {"admin"},
    "delete_records": {"admin"},
    "view_audit": {"admin", "supervisor"},
}


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    must_change_pw: bool = False

    def can(self, perm: str) -> bool:
        return self.role in PERMISSIONS.get(perm, set())

    @property
    def display(self) -> str:
        return self.full_name or self.username


SYSTEM = User(0, "system", "System", "admin")

# ----------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "company_name": "Your Company (Pvt) Ltd",
    "company_address": "",
    "company_logo": "",
    "tolerance_units": 0,
    "tolerance_pct": 0.0,
    "review_threshold": 0.45,
    "detector_model": "",
    "detector_conf": 0.35,
    "use_gpu": False,
    "inference_threads": 0,
    "frame_skip": 0,                # process every (n+1)th frame; raise on slow PCs
    "max_process_width": 960,
    "camera_offline_alert_s": 30,
    "tamper_enabled": True,
    "tamper_persist_s": 5,
    "preroll_s": 15,
    "clip_fps": 8,
    "truck_absent_close_s": 45,
    "truck_present_start_s": 5,
    "auto_close_on_truck_exit": True,
    "auto_plate_read": True,
    "report_show_company_name": False,   # with a logo: logo only (the name is usually in the logo)
    "sound_alerts": True,
    "alert_volume": 0.9,
    "language": "en",
    "theme": "light",
    # remote alerts
    "remote_events": ["mismatch", "camera_offline", "tamper"],
    "email_enabled": False, "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": "",
    "smtp_tls": True, "email_from": "", "email_to": "",
    "whatsapp_enabled": False, "whatsapp_token": "", "whatsapp_phone_id": "", "whatsapp_to": "",
    "sms_enabled": False, "sms_url_template": "", "sms_to": "",
    "paddle_rec_model": "", "paddle_rec_dict": "",
}
SECRET_SETTINGS = {"smtp_password", "whatsapp_token", "sms_url_template", "email_to", "whatsapp_to", "sms_to"}


class Settings:
    def __init__(self, db: Database):
        self.db = db
        self._cache: dict = {}
        self._lock = threading.Lock()

    def get(self, key: str, default=None):
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        v = self.db.get_setting(key, DEFAULT_SETTINGS.get(key, default))
        if key in SECRET_SETTINGS and isinstance(v, str):
            v = crypto.decrypt(v)
        with self._lock:
            self._cache[key] = v
        return v

    def set(self, key: str, value):
        stored = crypto.encrypt(value) if key in SECRET_SETTINGS and isinstance(value, str) else value
        self.db.set_setting(key, stored)
        with self._lock:
            self._cache[key] = value

    def all(self) -> dict:
        return {k: self.get(k) for k in DEFAULT_SETTINGS}


# ----------------------------------------------------------------- audit
def audit(db: Database, user: User | None, action: str, entity: str = "", entity_id="", details=None):
    u = user or SYSTEM
    if isinstance(details, (dict, list)):
        details = json.dumps(details, default=str)
    db.execute("INSERT INTO audit_log(ts, user_id, username, action, entity, entity_id, details) VALUES (?,?,?,?,?,?,?)",
               (time.time(), u.id or None, u.username, action, entity, str(entity_id or ""), details or ""))


# ----------------------------------------------------------------- auth
class AuthError(Exception):
    pass


class AuthService:
    MAX_ATTEMPTS = 5
    LOCK_S = 120

    def __init__(self, db: Database):
        self.db = db
        self._fails: dict[str, list[float]] = {}

    def ensure_default_admin(self) -> bool:
        """Create admin/admin123 (PIN 1234) on first run. Returns True if created."""
        if self.db.scalar("SELECT COUNT(*) FROM users") == 0:
            self.create_user("admin", "admin123", "admin", "Administrator", pin="1234", must_change=True, actor=SYSTEM)
            return True
        return False

    def _row_user(self, r) -> User:
        return User(r["id"], r["username"], r["full_name"], r["role"], bool(r["must_change_pw"]))

    def login(self, username: str, password: str) -> User:
        key = (username or "").lower()
        now = time.time()
        fails = [t for t in self._fails.get(key, []) if now - t < self.LOCK_S]
        if len(fails) >= self.MAX_ATTEMPTS:
            raise AuthError("Too many failed attempts. Please wait 2 minutes.")
        r = self.db.one("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,))
        if r is None or not r["active"] or not crypto.verify_secret(password, r["pw_hash"]):
            fails.append(now)
            self._fails[key] = fails
            audit(self.db, None, "login_failed", "user", username)
            raise AuthError("Incorrect username or password.")
        self._fails.pop(key, None)
        self.db.execute("UPDATE users SET last_login=? WHERE id=?", (now, r["id"]))
        u = self._row_user(r)
        audit(self.db, u, "login", "user", u.id)
        return u

    def verify_supervisor(self, username: str, pin: str) -> User:
        r = self.db.one("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,))
        if r is None or not r["active"] or r["role"] not in ("admin", "supervisor"):
            raise AuthError("Not a supervisor account.")
        if not crypto.verify_secret(pin, r["pin_hash"]):
            audit(self.db, None, "pin_failed", "user", username)
            raise AuthError("Incorrect PIN.")
        return self._row_user(r)

    def create_user(self, username: str, password: str, role: str, full_name: str = "", pin: str = "",
                    must_change: bool = False, actor: User | None = None) -> int:
        if role not in ROLES:
            raise ValueError("invalid role")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if role in ("admin", "supervisor") and pin and (not pin.isdigit() or len(pin) < 4):
            raise AuthError("PIN must be at least 4 digits.")
        uid = self.db.execute(
            "INSERT INTO users(username, full_name, role, pw_hash, pin_hash, must_change_pw, created_at) VALUES (?,?,?,?,?,?,?)",
            (username.strip(), full_name.strip(), role, crypto.hash_secret(password),
             crypto.hash_secret(pin) if pin else None, int(must_change), time.time()))
        audit(self.db, actor, "user_created", "user", uid, {"username": username, "role": role})
        return uid

    def update_user(self, uid: int, actor: User, full_name=None, role=None, active=None):
        r = self.db.one("SELECT * FROM users WHERE id=?", (uid,))
        if r is None:
            raise AuthError("User not found")
        if r["role"] == "admin" and (role not in (None, "admin") or active == 0):
            n_admins = self.db.scalar("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1")
            if n_admins <= 1:
                raise AuthError("At least one active Admin is required.")
        self.db.execute("UPDATE users SET full_name=COALESCE(?, full_name), role=COALESCE(?, role), "
                        "active=COALESCE(?, active) WHERE id=?", (full_name, role, active, uid))
        audit(self.db, actor, "user_updated", "user", uid, {"full_name": full_name, "role": role, "active": active})

    def set_password(self, uid: int, password: str, actor: User, must_change: bool = False):
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        self.db.execute("UPDATE users SET pw_hash=?, must_change_pw=? WHERE id=?",
                        (crypto.hash_secret(password), int(must_change), uid))
        audit(self.db, actor, "password_changed", "user", uid)

    def set_pin(self, uid: int, pin: str, actor: User):
        if not pin.isdigit() or len(pin) < 4:
            raise AuthError("PIN must be at least 4 digits.")
        self.db.execute("UPDATE users SET pin_hash=? WHERE id=?", (crypto.hash_secret(pin), uid))
        audit(self.db, actor, "pin_changed", "user", uid)

    def users(self):
        return self.db.q("SELECT id, username, full_name, role, active, last_login, created_at FROM users ORDER BY username")

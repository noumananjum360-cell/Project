"""Staff accounts, login with lock-out, first-run admin setup. No default credentials are ever created."""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.security.audit import audit
from app.security.passwords import hash_password, password_problem, verify_password
from app.security.permissions import ROLES, PermissionDenied, role_can

MAX_FAILURES = 5
LOCK_SECONDS = 300


class AuthError(Exception):
    pass


@dataclass
class Staff:
    id: int
    username: str
    full_name: str
    role: str
    active: bool = True
    must_change_password: bool = False

    @property
    def display(self) -> str:
        return self.full_name or self.username


SYSTEM = Staff(0, "system", "System", "Admin")


class AuthService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.user: Staff | None = None

    # ------------------------------------------------------------------ permissions
    def can(self, perm: str, user: Staff | None = None) -> bool:
        u = user or self.user
        return bool(u and u.active and role_can(u.role, perm, self.settings.all()))

    def require(self, perm: str, user: Staff | None = None) -> Staff:
        u = user or self.user
        if not self.can(perm, u):
            audit(self.db, u, "permission_denied", "permission", perm)
            raise PermissionDenied("You do not have permission to do this.")
        return u

    # ------------------------------------------------------------------ accounts
    def needs_first_run(self) -> bool:
        return not self.db.scalar("SELECT COUNT(*) FROM staff_users WHERE role='Admin' AND active=1", default=0)

    @staticmethod
    def _row(r) -> Staff:
        return Staff(r["id"], r["username"], r["full_name"], r["role"], bool(r["active"]), bool(r["must_change_password"]))

    def list(self) -> list[Staff]:
        return [self._row(r) for r in self.db.q("SELECT * FROM staff_users ORDER BY role, username")]

    def get(self, uid: int) -> Staff | None:
        r = self.db.one("SELECT * FROM staff_users WHERE id=?", (uid,))
        return self._row(r) if r else None

    def create(self, username: str, password: str, role: str, full_name: str = "", actor: Staff | None = None,
               first_run: bool = False) -> int:
        if not first_run:
            self.require("staff.manage", actor)
        elif not self.needs_first_run():
            raise AuthError("Setup has already been completed.")
        username = username.strip()
        if not username or len(username) > 40 or not all(ch.isalnum() or ch in "._-" for ch in username):
            raise AuthError("Username: 1-40 letters, numbers, dot, dash or underscore.")
        if role not in ROLES:
            raise AuthError("Unknown role.")
        if first_run and role != "Admin":
            raise AuthError("The first account must be an Admin.")
        problem = password_problem(password)
        if problem:
            raise AuthError(problem)
        if self.db.scalar("SELECT 1 FROM staff_users WHERE username=?", (username,)):
            raise AuthError("That username already exists.")
        now = time.time()
        uid = self.db.execute("INSERT INTO staff_users(username, full_name, role, password_hash, created_at, updated_at) "
                              "VALUES (?,?,?,?,?,?)", (username, full_name.strip(), role, hash_password(password), now, now))
        audit(self.db, actor or SYSTEM, "staff_created", "staff", uid, {"username": username, "role": role})
        return uid

    def update(self, uid: int, actor: Staff | None = None, **fields):
        actor = self.require("staff.manage", actor)
        allowed = {k: v for k, v in fields.items() if k in ("full_name", "role", "active")}
        if "role" in allowed and allowed["role"] not in ROLES:
            raise AuthError("Unknown role.")
        cur = self.get(uid)
        if cur is None:
            raise AuthError("Account not found.")
        losing_admin = cur.role == "Admin" and cur.active and (allowed.get("role", "Admin") != "Admin"
                                                               or allowed.get("active", True) is False)
        if losing_admin and self.db.scalar("SELECT COUNT(*) FROM staff_users WHERE role='Admin' AND active=1") <= 1:
            raise AuthError("At least one active Admin is required.")
        if uid == actor.id and allowed.get("active") is False:
            raise AuthError("You cannot disable your own account.")
        sets = ", ".join(f"{k}=?" for k in allowed)
        if sets:
            self.db.execute(f"UPDATE staff_users SET {sets}, updated_at=? WHERE id=?",
                            (*[int(v) if isinstance(v, bool) else v for v in allowed.values()], time.time(), uid))
            audit(self.db, actor, "staff_updated", "staff", uid, allowed)

    def reset_password(self, uid: int, new_password: str, actor: Staff | None = None):
        actor = self.require("staff.manage", actor)
        problem = password_problem(new_password)
        if problem:
            raise AuthError(problem)
        self.db.execute("UPDATE staff_users SET password_hash=?, must_change_password=1, failed_attempts=0, "
                        "locked_until=NULL, updated_at=? WHERE id=?", (hash_password(new_password), time.time(), uid))
        audit(self.db, actor, "staff_password_reset", "staff", uid)

    def change_own_password(self, old: str, new: str):
        if not self.user:
            raise AuthError("Not logged in.")
        r = self.db.one("SELECT password_hash FROM staff_users WHERE id=?", (self.user.id,))
        if not r or not verify_password(old, r["password_hash"]):
            raise AuthError("Current password is wrong.")
        problem = password_problem(new)
        if problem:
            raise AuthError(problem)
        self.db.execute("UPDATE staff_users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?",
                        (hash_password(new), time.time(), self.user.id))
        self.user.must_change_password = False
        audit(self.db, self.user, "password_changed", "staff", self.user.id)

    # ------------------------------------------------------------------ session
    def login(self, username: str, password: str) -> Staff:
        r = self.db.one("SELECT * FROM staff_users WHERE username=?", (username.strip(),))
        now = time.time()
        if r is None:
            audit(self.db, None, "login_failed", "staff", "", {"username": username.strip()[:40]})
            raise AuthError("Wrong username or password.")
        if not r["active"]:
            raise AuthError("This account is disabled. Ask an Admin.")
        if r["locked_until"] and r["locked_until"] > now:
            mins = int((r["locked_until"] - now) // 60) + 1
            raise AuthError(f"Too many failed attempts. Try again in {mins} minute(s).")
        if not verify_password(password, r["password_hash"]):
            fails = r["failed_attempts"] + 1
            lock = now + LOCK_SECONDS if fails >= MAX_FAILURES else None
            self.db.execute("UPDATE staff_users SET failed_attempts=?, locked_until=? WHERE id=?",
                            (0 if lock else fails, lock, r["id"]))
            audit(self.db, None, "login_failed", "staff", r["id"], {"username": r["username"], "locked": bool(lock)})
            raise AuthError("Too many failed attempts. The account is locked for 5 minutes." if lock
                            else "Wrong username or password.")
        self.db.execute("UPDATE staff_users SET failed_attempts=0, locked_until=NULL, last_login_at=? WHERE id=?",
                        (now, r["id"]))
        self.user = self._row(r)
        audit(self.db, self.user, "login", "staff", r["id"])
        return self.user

    def verify_current(self, password: str) -> bool:
        """Unlock a locked session."""
        if not self.user:
            return False
        r = self.db.one("SELECT password_hash FROM staff_users WHERE id=?", (self.user.id,))
        ok = bool(r and verify_password(password, r["password_hash"]))
        audit(self.db, self.user, "session_unlocked" if ok else "unlock_failed", "staff", self.user.id)
        return ok

    def logout(self):
        if self.user:
            audit(self.db, self.user, "logout", "staff", self.user.id)
        self.user = None

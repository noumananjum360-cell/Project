"""Append-only audit trail. Never pass passwords, tokens or biometric data in `details`."""
from __future__ import annotations

import json
import time

_FORBIDDEN = ("password", "token", "secret", "template", "embedding")


def _clean(details):
    if isinstance(details, dict):
        return {k: ("***" if any(f in k.lower() for f in _FORBIDDEN) else _clean(v)) for k, v in details.items()}
    return details


def audit(db, user, action: str, entity: str = "", entity_id="", details=None) -> None:
    db.execute("INSERT INTO audit_log(ts, user_id, username, action, entity, entity_id, details) VALUES (?,?,?,?,?,?,?)",
               (time.time(), getattr(user, "id", None), getattr(user, "username", "system") if user else "system",
                action, entity, str(entity_id if entity_id is not None else ""),
                json.dumps(_clean(details), ensure_ascii=False, default=str) if details is not None else ""))

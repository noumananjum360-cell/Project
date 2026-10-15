"""Admin-configurable system settings with defaults (stored in system_settings)."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import SystemSetting

DEFAULTS: dict[str, dict[str, Any]] = {
    "scoring_weights": {"skills": 30, "portfolio": 20, "experience": 15, "budget": 15, "scope": 10, "risk": 10},
    "scoring_thresholds": {
        "strong": 75,
        "possible": 50,
        "min_confidence": 0.5,
        "similarity_floor": 0.15,
        "similarity_ceiling": 0.6,
    },
    "ai_config": {"chat_model": None, "embedding_model": None, "timeout_seconds": None},
    "usage_limits": {"daily_ai_requests_per_user": 200},
}


def get_setting(db: Session | None, key: str) -> dict[str, Any]:
    value = copy.deepcopy(DEFAULTS.get(key, {}))
    if db is not None:
        row = db.get(SystemSetting, key)
        if row is not None and isinstance(row.value, dict):
            value.update(row.value)
    return value


def set_setting(db: Session, key: str, value: dict[str, Any], updated_by: uuid.UUID | None) -> dict[str, Any]:
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value, updated_by=updated_by)
        db.add(row)
    else:
        row.value = value
        row.updated_by = updated_by
    db.flush()
    return get_setting(db, key)

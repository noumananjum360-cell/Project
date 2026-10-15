from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: Any = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an audit event. Never pass secrets or user content in ``details``."""
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=(request.client.host if request and request.client else None),
            details=details or {},
        )
    )

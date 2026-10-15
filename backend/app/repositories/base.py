"""Ownership-scoped data access helpers.

Every user-owned lookup goes through these helpers so that a record belonging
to another user is indistinguishable from a missing record (404, not 403).
"""

from __future__ import annotations

import math
import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError

T = TypeVar("T")


def get_owned(db: Session, model: type[T], obj_id: uuid.UUID, user_id: uuid.UUID, label: str = "Resource") -> T:
    obj = db.scalar(select(model).where(model.id == obj_id, model.user_id == user_id))  # type: ignore[attr-defined,arg-type]
    if obj is None:
        raise NotFoundError(f"{label} not found.")
    return obj


def paginate(db: Session, stmt: Select[Any], page: int, page_size: int) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)) if page_size else 1,
    }

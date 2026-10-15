from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbSession
from app.models import Notification
from app.repositories.base import get_owned, paginate
from app.schemas.common import Message
from app.schemas.proposals import NotificationOut
from app.services.notifications import generate_follow_up_reminders

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    generate_follow_up_reminders(db, user.id)
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    result = paginate(db, stmt.order_by(Notification.created_at.desc()), page, page_size)
    result["items"] = [NotificationOut.model_validate(n) for n in result["items"]]
    result["unread"] = int(
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    return result


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Notification:
    n = get_owned(db, Notification, notification_id, user.id, "Notification")
    n.read_at = n.read_at or datetime.now(UTC)
    db.commit()
    return n


@router.post("/read-all", response_model=Message)
def mark_all_read(user: CurrentUser, db: DbSession) -> Message:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return Message(message="All notifications marked as read.")

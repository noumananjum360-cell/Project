from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationTracking, Job, Notification, UserPreferences


def notify(
    db: Session,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str | None = None,
    *,
    link: str | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Create a notification; silently skip if one with the same dedupe key already exists."""
    if dedupe_key and db.scalar(
        select(Notification.id).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
    ):
        return None
    n = Notification(user_id=user_id, type=type_, title=title, body=body, link=link, dedupe_key=dedupe_key)
    db.add(n)
    return n


def generate_follow_up_reminders(db: Session, user_id: uuid.UUID) -> int:
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
    if prefs is not None and not prefs.notify_follow_ups:
        return 0
    now = datetime.now(UTC)
    due = db.execute(
        select(ApplicationTracking, Job.title)
        .join(Job, Job.id == ApplicationTracking.job_id)
        .where(
            ApplicationTracking.user_id == user_id,
            ApplicationTracking.follow_up_at.is_not(None),
            ApplicationTracking.follow_up_at <= now,
            ApplicationTracking.follow_up_notified_at.is_(None),
        )
    ).all()
    for app_row, title in due:
        notify(
            db,
            user_id,
            "follow_up",
            f"Follow up: {title[:150]}",
            "You scheduled a follow-up for this application.",
            link="/tracker",
            dedupe_key=f"follow_up:{app_row.id}:{app_row.follow_up_at}",
        )
        app_row.follow_up_notified_at = now
    if due:
        db.commit()
    return len(due)

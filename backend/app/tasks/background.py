"""Background work executed after the response (FastAPI BackgroundTasks).

Runs in-process with its own database session. For heavier workloads, these
functions can be moved to a Redis-backed worker without code changes to the
services they call (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Job, User
from app.services.analysis_service import analyze_job

log = get_logger(__name__)


def auto_analyze_jobs(user_id: uuid.UUID, job_ids: list[uuid.UUID]) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return
        try:
            provider = get_ai_provider(db)
        except AppError as exc:
            log.info("auto_analyze_skipped", reason=exc.code)
            return
        for job in db.scalars(select(Job).where(Job.user_id == user_id, Job.id.in_(job_ids)).limit(50)):
            try:
                analyze_job(db, provider, user, job)
            except AppError as exc:
                db.rollback()
                log.info("auto_analyze_failed", code=exc.code)
                if exc.code in {"ai_not_configured", "usage_limit_reached", "ai_auth_failed"}:
                    return
    finally:
        db.close()

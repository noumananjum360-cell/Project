"""Account-level privacy operations: data export and account deletion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.v1.auth import _clear_session_cookies
from app.core.errors import AuthError
from app.core.logging import get_logger
from app.models import (
    ApplicationStatusHistory,
    ApplicationTracking,
    Job,
    JobAnalysis,
    Notification,
    PortfolioProject,
    Proposal,
    ProposalVersion,
    Resume,
    UserPreferences,
    UserProfile,
)
from app.schemas.auth import DeleteAccountIn
from app.schemas.common import Message
from app.security.passwords import verify_password
from app.security.rate_limit import auth_rate_limit
from app.services import resume_service
from app.services.audit import audit
from app.vector_store.factory import get_vector_store

log = get_logger(__name__)
router = APIRouter(prefix="/account", tags=["account"])

_SKIP = {"user_id", "password_hash", "storage_path", "extracted_text"}


def _row(obj: Any) -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in obj.__mapper__.column_attrs if c.key not in _SKIP}


@router.get("/export")
def export_data(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Export all of the user's data as JSON (passwords, tokens and raw files are excluded)."""
    uid = user.id

    def rows(model: Any) -> list[dict[str, Any]]:
        return [_row(o) for o in db.scalars(select(model).where(model.user_id == uid))]

    return {
        "account": {"email": user.email, "full_name": user.full_name, "role": user.role, "created_at": user.created_at},
        "profile": rows(UserProfile),
        "preferences": rows(UserPreferences),
        "resumes": rows(Resume),
        "portfolio_projects": rows(PortfolioProject),
        "jobs": rows(Job),
        "job_analyses": rows(JobAnalysis),
        "proposals": rows(Proposal),
        "proposal_versions": rows(ProposalVersion),
        "applications": rows(ApplicationTracking),
        "application_status_history": rows(ApplicationStatusHistory),
        "notifications": rows(Notification),
    }


@router.delete("", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def delete_account(body: DeleteAccountIn, request: Request, response: Response, user: CurrentUser, db: DbSession) -> Message:
    """Permanently delete the account and all user-owned data, files and vectors."""
    if not verify_password(body.password, user.password_hash):
        raise AuthError("Password is incorrect.", code="invalid_credentials")
    for r in db.scalars(select(Resume).where(Resume.user_id == user.id)):
        resume_service.delete_file(r)
    try:
        get_vector_store().delete_user(user_id=str(user.id))
    except Exception:  # noqa: BLE001
        log.error("vector_delete_user_failed")
    audit(db, "account.deleted", actor_id=None, target_type="user", target_id=user.id, request=request)
    db.delete(user)  # cascades to all user-owned rows
    db.commit()
    _clear_session_cookies(response)
    return Message(message="Your account and data have been deleted.")

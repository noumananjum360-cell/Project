from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ConflictError
from app.models import ApplicationStatusHistory, ApplicationTracking, Job, Proposal
from app.repositories.base import get_owned, paginate
from app.schemas.common import Message, Page
from app.schemas.proposals import ApplicationCreate, ApplicationOut, ApplicationUpdate, StatusHistoryOut

router = APIRouter(prefix="/applications", tags=["applications"])


def _out(db: DbSession, a: ApplicationTracking, with_history: bool = False) -> ApplicationOut:
    out = ApplicationOut.model_validate(a)
    job = db.get(Job, a.job_id)
    if job is not None and job.user_id == a.user_id:
        out.job_title = job.title
        out.job_fit_score = job.latest_fit_score
    if with_history:
        out.history = [
            StatusHistoryOut.model_validate(h)
            for h in db.scalars(
                select(ApplicationStatusHistory)
                .where(ApplicationStatusHistory.application_id == a.id)
                .order_by(ApplicationStatusHistory.created_at.desc())
            )
        ]
    return out


@router.get("", response_model=Page[ApplicationOut])
def list_applications(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status", max_length=100),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    stmt = (
        select(ApplicationTracking)
        .join(Job, Job.id == ApplicationTracking.job_id)
        .where(ApplicationTracking.user_id == user.id, Job.user_id == user.id)
    )
    if status_filter:
        stmt = stmt.where(ApplicationTracking.status.in_([s.strip() for s in status_filter.split(",")]))
    if q:
        stmt = stmt.where(or_(Job.title.ilike(f"%{q}%"), ApplicationTracking.notes.ilike(f"%{q}%")))
    result = paginate(db, stmt.order_by(ApplicationTracking.updated_at.desc()), page, page_size)
    result["items"] = [_out(db, a) for a in result["items"]]
    return result


def _proposal_version(db: DbSession, user_id: uuid.UUID, proposal_id: uuid.UUID | None, job_id: uuid.UUID) -> int | None:
    if proposal_id is None:
        return None
    p = get_owned(db, Proposal, proposal_id, user_id, "Proposal")
    if p.job_id != job_id:
        raise ConflictError("The proposal belongs to a different job.", code="proposal_job_mismatch")
    return p.current_version_number


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationCreate, user: CurrentUser, db: DbSession) -> ApplicationOut:
    """Start tracking an application. Status values are entered by the user; nothing is submitted automatically."""
    get_owned(db, Job, body.job_id, user.id, "Job")
    existing = db.scalar(
        select(ApplicationTracking).where(ApplicationTracking.user_id == user.id, ApplicationTracking.job_id == body.job_id)
    )
    if existing:
        raise ConflictError(
            "This job is already being tracked.", code="application_exists", details={"existing_application_id": str(existing.id)}
        )
    a = ApplicationTracking(
        user_id=user.id,
        job_id=body.job_id,
        proposal_id=body.proposal_id,
        proposal_version_number=_proposal_version(db, user.id, body.proposal_id, body.job_id),
        status=body.status,
        notes=body.notes,
        follow_up_at=body.follow_up_at,
        submitted_at=datetime.now(UTC) if body.status == "sent" else None,
    )
    db.add(a)
    db.flush()
    db.add(ApplicationStatusHistory(application_id=a.id, user_id=user.id, from_status=None, to_status=body.status))
    db.commit()
    return _out(db, a, with_history=True)


@router.get("/{application_id}", response_model=ApplicationOut)
def get_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    return _out(db, get_owned(db, ApplicationTracking, application_id, user.id, "Application"), with_history=True)


@router.put("/{application_id}", response_model=ApplicationOut)
def update_application(application_id: uuid.UUID, body: ApplicationUpdate, user: CurrentUser, db: DbSession) -> ApplicationOut:
    a = get_owned(db, ApplicationTracking, application_id, user.id, "Application")
    data = body.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    note = data.pop("status_note", None)
    if "proposal_id" in data:
        a.proposal_version_number = _proposal_version(db, user.id, data["proposal_id"], a.job_id)
    if "follow_up_at" in data and data["follow_up_at"] != a.follow_up_at:
        a.follow_up_notified_at = None
    for k, v in data.items():
        setattr(a, k, v)
    if new_status and new_status != a.status:
        db.add(
            ApplicationStatusHistory(application_id=a.id, user_id=user.id, from_status=a.status, to_status=new_status, note=note)
        )
        if new_status == "sent" and a.submitted_at is None and "submitted_at" not in data:
            a.submitted_at = datetime.now(UTC)
        a.status = new_status
        job = db.get(Job, a.job_id)
        if job is not None and new_status in {"sent", "interview", "hired"} and job.status in {"new", "saved", "shortlisted"}:
            job.status = "applied"
    db.commit()
    db.refresh(a)
    return _out(db, a, with_history=True)


@router.delete("/{application_id}", response_model=Message)
def delete_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    a = get_owned(db, ApplicationTracking, application_id, user.id, "Application")
    db.delete(a)
    db.commit()
    return Message(message="Application tracking removed.")

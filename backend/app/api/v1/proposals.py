from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select

from app.ai.factory import get_ai_provider
from app.api.deps import AIUser, CurrentUser, DbSession
from app.models import ApplicationTracking, Job, Proposal, ProposalVersion, UserProfile
from app.repositories.base import get_owned, paginate
from app.schemas.common import Message, Page
from app.schemas.jobs import ProposalGenerateIn
from app.schemas.proposals import (
    ProposalListItem,
    ProposalOut,
    ProposalRegenerateIn,
    ProposalUpdate,
    ProposalVersionOut,
)
from app.services import proposal_service

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _defaults(db: DbSession, user_id: uuid.UUID) -> tuple[str, str]:
    p = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    return (p.proposal_tone, p.proposal_length) if p else ("professional", "standard")


@router.get("", response_model=Page[ProposalListItem])
def list_proposals(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    job_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    stmt = select(Proposal).where(Proposal.user_id == user.id)
    if q:
        stmt = stmt.where(or_(Proposal.title.ilike(f"%{q}%"), Proposal.content.ilike(f"%{q}%")))
    if job_id:
        stmt = stmt.where(Proposal.job_id == job_id)
    result = paginate(db, stmt.order_by(Proposal.updated_at.desc()), page, page_size)
    job_ids = {p.job_id for p in result["items"]}
    titles = (
        dict(db.execute(select(Job.id, Job.title).where(Job.id.in_(job_ids), Job.user_id == user.id)).all()) if job_ids else {}
    )
    statuses = (
        dict(
            db.execute(
                select(ApplicationTracking.job_id, ApplicationTracking.status).where(
                    ApplicationTracking.user_id == user.id, ApplicationTracking.job_id.in_(job_ids)
                )
            ).all()
        )
        if job_ids
        else {}
    )
    items = []
    for p in result["items"]:
        item = ProposalListItem.model_validate(p)
        item.job_title = titles.get(p.job_id)
        item.application_status = statuses.get(p.job_id)
        items.append(item)
    result["items"] = items
    return result


@router.post("/generate", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def generate(body: ProposalGenerateIn, user: AIUser, db: DbSession) -> Proposal:
    """Generate a Hook → Solution → Proof → Call-to-Action proposal from verified user data."""
    job = get_owned(db, Job, body.job_id, user.id, "Job")
    tone, length = _defaults(db, user.id)
    options = body.model_dump(exclude={"job_id"}, mode="json")
    options["tone"] = body.tone or tone
    options["length"] = body.length or length
    provider = get_ai_provider(db)
    return proposal_service.generate_proposal(db, provider, user, job, options)


@router.get("/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Proposal:
    return get_owned(db, Proposal, proposal_id, user.id, "Proposal")


@router.put("/{proposal_id}", response_model=ProposalOut)
def update_proposal(proposal_id: uuid.UUID, body: ProposalUpdate, user: CurrentUser, db: DbSession) -> Proposal:
    """Save edits (used by autosave). Does not create a version; use POST /versions to snapshot."""
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    p.content = body.content
    if body.title:
        p.title = body.title
    if body.sections is not None:
        p.sections = {**p.sections, **{str(k): v for k, v in body.sections.items()}}
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{proposal_id}", response_model=Message)
def delete_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    db.delete(p)
    db.commit()
    return Message(message="Proposal deleted.")


@router.post("/{proposal_id}/regenerate", response_model=ProposalOut)
def regenerate(proposal_id: uuid.UUID, body: ProposalRegenerateIn, user: AIUser, db: DbSession) -> Proposal:
    """Regenerate the whole proposal or one section. The previous text remains in version history."""
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    options = {**p.options, **body.model_dump(exclude={"section"}, exclude_none=True, mode="json")}
    options["tone"] = body.tone or p.tone
    options["length"] = body.length or p.length
    # Make sure the latest manual edits are preserved in history before overwriting.
    latest = db.scalar(
        select(ProposalVersion)
        .where(ProposalVersion.proposal_id == p.id)
        .order_by(ProposalVersion.version_number.desc())
        .limit(1)
    )
    if latest is None or latest.content != p.content:
        proposal_service.snapshot_version(db, p)
    provider = get_ai_provider(db)
    return proposal_service.regenerate_proposal(db, provider, user, p, options, body.section)


@router.post("/{proposal_id}/versions", response_model=ProposalVersionOut, status_code=status.HTTP_201_CREATED)
def create_version(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProposalVersion:
    """Snapshot the current (edited) content as a new version."""
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    return proposal_service.snapshot_version(db, p)


@router.get("/{proposal_id}/versions", response_model=list[ProposalVersionOut])
def list_versions(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[ProposalVersion]:
    get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    return list(
        db.scalars(
            select(ProposalVersion)
            .where(ProposalVersion.proposal_id == proposal_id, ProposalVersion.user_id == user.id)
            .order_by(ProposalVersion.version_number.desc())
        )
    )


@router.post("/{proposal_id}/versions/{version_number}/restore", response_model=ProposalOut)
def restore_version(proposal_id: uuid.UUID, version_number: int, user: CurrentUser, db: DbSession) -> Proposal:
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    v = db.scalar(
        select(ProposalVersion).where(ProposalVersion.proposal_id == p.id, ProposalVersion.version_number == version_number)
    )
    if v is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Version not found.")
    p.content = v.content
    p.sections = dict(v.sections)
    proposal_service.snapshot_version(db, p)
    db.refresh(p)
    return p


@router.get("/{proposal_id}/export", response_class=PlainTextResponse)
def export(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession, format: Literal["txt", "md"] = "txt") -> PlainTextResponse:
    p = get_owned(db, Proposal, proposal_id, user.id, "Proposal")
    body = p.content if format == "txt" else f"# {p.title}\n\n{p.content}\n"
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", p.title)[:60].strip("-") or "proposal"
    media = "text/plain" if format == "txt" else "text/markdown"
    return PlainTextResponse(
        body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'},
    )

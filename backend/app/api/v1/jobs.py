from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from sqlalchemy import String, and_, cast, not_, nulls_last, or_, select

from app.ai.factory import get_ai_provider
from app.api.deps import AIUser, CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.models import Job, JobAnalysis, JobImport, PortfolioProject, UserPreferences, UserProfile
from app.repositories.base import get_owned, paginate
from app.schemas.common import Message, Page
from app.schemas.jobs import (
    AnalysisOut,
    JobCreate,
    JobExtensionCreate,
    JobImportOut,
    JobOut,
    JobStatusUpdate,
    JobUpdate,
    ParseTextIn,
    PortfolioMatchOut,
)
from app.services import job_service, portfolio_index
from app.services.analysis_service import analyze_job
from app.tasks.background import auto_analyze_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobOut])
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200, description="Include keywords (all must match)"),
    exclude: str | None = Query(default=None, max_length=200, description="Exclude keywords (comma separated)"),
    skills: str | None = Query(default=None, max_length=300, description="Required skills (comma separated)"),
    budget_min: Decimal | None = Query(default=None, ge=0),
    budget_max: Decimal | None = Query(default=None, ge=0),
    job_type: Literal["hourly", "fixed", "unknown"] | None = None,
    experience_level: Literal["entry", "intermediate", "expert", "unknown"] | None = None,
    posted_after: datetime | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    analyzed: bool | None = None,
    status_filter: str | None = Query(
        default=None, alias="status", max_length=100, description="Comma-separated statuses; 'archived' excluded unless requested"
    ),
    source: str | None = Query(default=None, max_length=20),
    sort: Literal["newest", "oldest", "score", "budget", "posted"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    stmt = select(Job).where(Job.user_id == user.id)
    if q:
        for word in q.split():
            like = f"%{word}%"
            stmt = stmt.where(or_(Job.title.ilike(like), Job.description.ilike(like)))
    if exclude:
        for word in [w.strip() for w in exclude.split(",") if w.strip()]:
            like = f"%{word}%"
            stmt = stmt.where(not_(or_(Job.title.ilike(like), Job.description.ilike(like))))
    if skills:
        for s in [w.strip() for w in skills.split(",") if w.strip()]:
            stmt = stmt.where(cast(Job.required_skills, String).ilike(f"%{s}%"))
    if budget_min is not None:
        stmt = stmt.where(or_(Job.budget_max >= budget_min, and_(Job.budget_max.is_(None), Job.budget_min >= budget_min)))
    if budget_max is not None:
        stmt = stmt.where(or_(Job.budget_min <= budget_max, and_(Job.budget_min.is_(None), Job.budget_max <= budget_max)))
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    if experience_level:
        stmt = stmt.where(Job.experience_level == experience_level)
    if posted_after:
        stmt = stmt.where(Job.posted_at >= posted_after)
    if min_score is not None:
        stmt = stmt.where(Job.latest_fit_score >= min_score)
    if analyzed is not None:
        stmt = stmt.where(Job.analyzed_at.is_not(None) if analyzed else Job.analyzed_at.is_(None))
    if status_filter:
        stmt = stmt.where(Job.status.in_([s.strip() for s in status_filter.split(",")]))
    else:
        stmt = stmt.where(Job.status != "archived")
    if source:
        stmt = stmt.where(Job.source == source)
    order: Any = {
        "newest": Job.created_at.desc(),
        "oldest": Job.created_at.asc(),
        "score": nulls_last(Job.latest_fit_score.desc()),
        "budget": nulls_last(Job.budget_max.desc()),
        "posted": nulls_last(Job.posted_at.desc()),
    }[sort]
    return paginate(db, stmt.order_by(order, Job.id), page, page_size)


def _maybe_auto_analyze(db: DbSession, user: CurrentUser, job_ids: list[uuid.UUID], background: BackgroundTasks) -> None:
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    if prefs and prefs.auto_analyze_on_import and job_ids:
        background.add_task(auto_analyze_jobs, user.id, job_ids)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    source: Literal["manual", "paste"] = "manual",
) -> Job:
    """Manually create a job (or save a reviewed pasted job). Duplicates return 409 with the existing id."""
    job = job_service.create_single_job(db, user.id, body, source=source)
    _maybe_auto_analyze(db, user, [job.id], background)
    return job


@router.post("/from-extension", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_from_extension(body: JobExtensionCreate, user: CurrentUser, db: DbSession, background: BackgroundTasks) -> Job:
    """Save job details the user extracted from a visible page with the browser extension."""
    data = JobCreate.model_validate(body.model_dump(exclude={"source_page"}))
    job = job_service.create_single_job(db, user.id, data, source="extension")
    _maybe_auto_analyze(db, user, [job.id], background)
    return job


@router.post("/parse-text", response_model=dict)
def parse_text(body: ParseTextIn, user: CurrentUser) -> dict:
    """Extract likely fields from a pasted job post for the user to review. Nothing is saved."""
    return job_service.parse_job_text(body.text)


@router.post("/import/csv", response_model=JobImportOut, status_code=status.HTTP_201_CREATED)
async def import_csv(user: CurrentUser, db: DbSession, background: BackgroundTasks, file: UploadFile = File(...)) -> JobImport:
    limit = get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise AppError("CSV file is too large.", code="file_too_large", status_code=413)
    if not (file.filename or "").lower().endswith(".csv"):
        raise AppError("Please upload a .csv file.", code="invalid_file_type")
    imp = job_service.import_csv(db, user.id, content, file.filename)
    new_ids = list(db.scalars(select(Job.id).where(Job.import_id == imp.id)))
    _maybe_auto_analyze(db, user, new_ids, background)
    return imp


@router.get("/imports", response_model=list[JobImportOut])
def list_imports(user: CurrentUser, db: DbSession) -> list[JobImport]:
    return list(db.scalars(select(JobImport).where(JobImport.user_id == user.id).order_by(JobImport.created_at.desc()).limit(50)))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Job:
    return get_owned(db, Job, job_id, user.id, "Job")


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: uuid.UUID, body: JobUpdate, user: CurrentUser, db: DbSession) -> Job:
    job = get_owned(db, Job, job_id, user.id, "Job")
    data = body.model_dump()
    data["client_info"] = body.client_info.model_dump(exclude_none=True) if body.client_info else {}
    for k, v in data.items():
        setattr(job, k, v)
    job.normalized_url = job_service.normalize_url(body.url)
    job.fingerprint = job_service.fingerprint(body.title, body.description)
    dup = db.scalar(
        select(Job.id).where(
            Job.user_id == user.id,
            Job.id != job.id,
            or_(
                Job.fingerprint == job.fingerprint,
                and_(Job.normalized_url.is_not(None), Job.normalized_url == job.normalized_url),
            ),
        )
    )
    if dup:
        db.rollback()
        raise AppError(
            "Another saved job has the same URL or content.",
            code="duplicate_job",
            status_code=409,
            details={"existing_job_id": str(dup)},
        )
    db.commit()
    db.refresh(job)
    return job


@router.patch("/{job_id}", response_model=JobOut)
def update_job_status(job_id: uuid.UUID, body: JobStatusUpdate, user: CurrentUser, db: DbSession) -> Job:
    """Update only status and/or notes (e.g. save, archive)."""
    job = get_owned(db, Job, job_id, user.id, "Job")
    if body.status is not None:
        job.status = body.status
    if body.notes is not None:
        job.notes = body.notes
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", response_model=Message)
def delete_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    job = get_owned(db, Job, job_id, user.id, "Job")
    db.delete(job)
    db.commit()
    return Message(message="Job deleted.")


def _analysis_out(db: DbSession, user: CurrentUser, a: JobAnalysis) -> AnalysisOut:
    out = AnalysisOut.model_validate(a)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    latest_project = db.scalar(
        select(PortfolioProject.updated_at)
        .where(PortfolioProject.user_id == user.id)
        .order_by(PortfolioProject.updated_at.desc())
        .limit(1)
    )
    out.profile_changed_since = bool(
        (profile and a.profile_version is not None and profile.profile_version != a.profile_version)
        or (latest_project and latest_project > a.created_at)
    )
    return out


@router.post("/{job_id}/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def analyze(job_id: uuid.UUID, user: AIUser, db: DbSession) -> AnalysisOut:
    """Run (or re-run) the Fit Score analysis. Requires a configured AI provider (embeddings)."""
    job = get_owned(db, Job, job_id, user.id, "Job")
    provider = get_ai_provider(db)
    return _analysis_out(db, user, analyze_job(db, provider, user, job))


@router.get("/{job_id}/analysis", response_model=AnalysisOut)
def latest_analysis(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AnalysisOut:
    get_owned(db, Job, job_id, user.id, "Job")
    a = db.scalar(
        select(JobAnalysis)
        .where(JobAnalysis.job_id == job_id, JobAnalysis.user_id == user.id)
        .order_by(JobAnalysis.created_at.desc())
        .limit(1)
    )
    if a is None:
        raise NotFoundError("This job has not been analyzed yet.")
    return _analysis_out(db, user, a)


@router.get("/{job_id}/analyses", response_model=list[AnalysisOut])
def analysis_history(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[AnalysisOut]:
    get_owned(db, Job, job_id, user.id, "Job")
    rows = db.scalars(
        select(JobAnalysis)
        .where(JobAnalysis.job_id == job_id, JobAnalysis.user_id == user.id)
        .order_by(JobAnalysis.created_at.desc())
        .limit(20)
    )
    return [AnalysisOut.model_validate(a) for a in rows]


@router.post("/{job_id}/match-portfolio", response_model=list[PortfolioMatchOut])
def match(job_id: uuid.UUID, user: AIUser, db: DbSession, top_k: int = Query(default=3, ge=1, le=10)) -> list[dict]:
    """Semantic search over the user's own portfolio for this job."""
    job = get_owned(db, Job, job_id, user.id, "Job")
    provider = get_ai_provider(db)
    return portfolio_index.match_portfolio(db, provider, user.id, job, top_k=top_k)

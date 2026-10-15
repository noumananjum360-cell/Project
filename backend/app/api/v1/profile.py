from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from app.api.deps import AIUser, CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.models import Resume, UserPreferences, UserProfile
from app.schemas.common import Message
from app.schemas.profile import PreferencesIn, PreferencesOut, ProfileIn, ProfileOut, ResumeApplyIn, ResumeOut
from app.services import resume_service

router = APIRouter(prefix="/profile", tags=["profile"])

SCORING_FIELDS = {"primary_skills", "additional_skills", "years_experience", "hourly_rate", "min_budget", "currency"}


def _get_or_create_profile(db: DbSession, user: CurrentUser) -> UserProfile:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(user_id=user.id, full_name=user.full_name)
        db.add(profile)
        db.flush()
    return profile


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> UserProfile:
    profile = _get_or_create_profile(db, user)
    db.commit()
    return profile


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileIn, user: CurrentUser, db: DbSession) -> UserProfile:
    profile = _get_or_create_profile(db, user)
    changed_scoring = False
    for field, value in body.model_dump().items():
        if getattr(profile, field) != value:
            if field in SCORING_FIELDS:
                changed_scoring = True
            setattr(profile, field, value)
    if changed_scoring:
        profile.profile_version += 1
    if body.full_name:
        user.full_name = body.full_name
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("", response_model=Message)
def clear_profile(user: CurrentUser, db: DbSession) -> Message:
    """Reset all profile fields (the account itself is kept)."""
    profile = _get_or_create_profile(db, user)
    defaults = ProfileIn().model_dump()
    for field, value in defaults.items():
        setattr(profile, field, value)
    profile.profile_version += 1
    db.commit()
    return Message(message="Profile data cleared.")


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: CurrentUser, db: DbSession) -> UserPreferences:
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
    return prefs


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesIn, user: CurrentUser, db: DbSession) -> UserPreferences:
    prefs = get_preferences(user, db)
    for k, v in body.model_dump().items():
        setattr(prefs, k, v)
    db.commit()
    return prefs


def _resume_out(r: Resume) -> ResumeOut:
    out = ResumeOut.model_validate(r)
    out.file_retained = bool(r.storage_path)
    return out


@router.post("/resume", response_model=ResumeOut, status_code=201)
async def upload_resume(user: AIUser, db: DbSession, file: UploadFile = File(...)) -> ResumeOut:
    """Upload a PDF/DOCX resume. Extracted data is returned for review; nothing is applied automatically."""
    limit = get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"File exceeds the {get_settings().MAX_UPLOAD_SIZE_MB} MB limit.", code="file_too_large", status_code=413)
    resume = resume_service.process_upload(db, user, file.filename or "resume", data)
    return _resume_out(resume)


def _latest_resume(db: DbSession, user: CurrentUser) -> Resume:
    r = db.scalar(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()).limit(1))
    if r is None:
        raise NotFoundError("No resume uploaded.")
    return r


@router.get("/resume", response_model=ResumeOut)
def get_resume(user: CurrentUser, db: DbSession) -> ResumeOut:
    return _resume_out(_latest_resume(db, user))


@router.post("/resume/apply", response_model=ProfileOut)
def apply_resume(body: ResumeApplyIn, user: CurrentUser, db: DbSession) -> UserProfile:
    """Apply only the fields the user confirmed on the review screen."""
    resume = _latest_resume(db, user)
    if resume.status not in {"parsed", "applied"}:
        raise AppError("This resume has not been parsed successfully.", code="resume_not_parsed")
    profile = _get_or_create_profile(db, user)
    for field in ("full_name", "headline", "overview", "years_experience"):
        val = getattr(body, field)
        if val is not None and val != "":
            setattr(profile, field, val)
    profile.primary_skills = list(dict.fromkeys(profile.primary_skills + body.add_primary_skills))[:40]
    profile.additional_skills = [
        s for s in dict.fromkeys(profile.additional_skills + body.add_additional_skills) if s not in profile.primary_skills
    ][:60]
    profile.languages = list(dict.fromkeys(profile.languages + body.languages))[:30]
    profile.profile_version += 1
    resume.status = "applied"
    resume.applied_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/resume", response_model=Message)
def delete_resume(user: CurrentUser, db: DbSession) -> Message:
    """Delete all uploaded resumes, their stored files and extracted text."""
    resumes = list(db.scalars(select(Resume).where(Resume.user_id == user.id)))
    if not resumes:
        raise NotFoundError("No resume uploaded.")
    for r in resumes:
        resume_service.delete_file(r)
        db.delete(r)
    db.commit()
    return Message(message="Resume data deleted.")

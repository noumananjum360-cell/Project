"""Job import, normalisation and de-duplication."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError
from app.models import Job, JobImport
from app.schemas.jobs import JobCreate
from app.services.skills import extract_skills_from_text

_UPWORK_ID = re.compile(r"~0?([0-9a-f]{12,})", re.I)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        return None
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    m = _UPWORK_ID.search(parts.path)
    if host.endswith("upwork.com") and m:
        return f"upwork.com/jobs/~{m.group(1).lower()}"
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit(("", host, path, "", "")).lstrip("/")


def fingerprint(title: str, description: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", f"{title}\n{description}".lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


def find_duplicate(db: Session, user_id: uuid.UUID, norm_url: str | None, fp: str) -> Job | None:
    conds = [Job.fingerprint == fp]
    if norm_url:
        conds.append(Job.normalized_url == norm_url)
    return db.scalar(select(Job).where(Job.user_id == user_id, or_(*conds)).limit(1))


def create_job(
    db: Session,
    user_id: uuid.UUID,
    data: JobCreate,
    *,
    source: str,
    import_id: uuid.UUID | None = None,
    is_demo: bool = False,
) -> tuple[Job, bool]:
    """Create a job, or return (existing, False) when it is a duplicate."""
    norm = normalize_url(data.url)
    fp = fingerprint(data.title, data.description)
    dup = find_duplicate(db, user_id, norm, fp)
    if dup is not None:
        return dup, False
    skills = data.required_skills
    job = Job(
        user_id=user_id,
        import_id=import_id,
        title=data.title,
        description=data.description,
        budget_min=data.budget_min,
        budget_max=data.budget_max,
        currency=data.currency,
        job_type=data.job_type,
        required_skills=skills,
        experience_level=data.experience_level,
        client_info=data.client_info.model_dump(exclude_none=True) if data.client_info else {},
        proposals_info=data.proposals_info,
        posted_at=data.posted_at,
        url=data.url,
        normalized_url=norm,
        fingerprint=fp,
        source=source,
        notes=data.notes,
        is_demo=is_demo,
    )
    db.add(job)
    db.flush()
    return job, True


def create_single_job(db: Session, user_id: uuid.UUID, data: JobCreate, source: str) -> Job:
    imp = JobImport(user_id=user_id, source=source, total_rows=1)
    db.add(imp)
    db.flush()
    job, created = create_job(db, user_id, data, source=source, import_id=imp.id)
    if not created:
        db.rollback()
        raise ConflictError("This job has already been imported.", code="duplicate_job", details={"existing_job_id": str(job.id)})
    imp.created_count = 1
    db.commit()
    db.refresh(job)
    return job


# --- Text parsing (pasted job posts) ------------------------------------------
_MONEY = r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s?(k)?"


def _money(v: str, k: str | None) -> Decimal:
    d = Decimal(v.replace(",", ""))
    return d * 1000 if k else d


def parse_job_text(text: str) -> dict[str, Any]:
    """Best-effort extraction of structured fields from a pasted job post (user reviews the result)."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    out: dict[str, Any] = {
        "title": lines[0][:300] if lines else "",
        "description": "\n".join(lines[1:]) if len(lines) > 1 else text.strip(),
        "job_type": "unknown",
        "experience_level": "unknown",
        "required_skills": extract_skills_from_text(text, limit=15),
        "budget_min": None,
        "budget_max": None,
    }
    m = re.search(_MONEY + r"\s?-\s?" + _MONEY + r"\s?(/\s?hr|per hour|hourly|/hour)", text, re.I)
    if m:
        out.update(
            job_type="hourly", budget_min=str(_money(m.group(1), m.group(2))), budget_max=str(_money(m.group(3), m.group(4)))
        )
    else:
        m = re.search(r"hourly[^\n$]{0,20}" + _MONEY + r"\s?-\s?" + _MONEY, text, re.I)
        if m:
            out.update(
                job_type="hourly", budget_min=str(_money(m.group(1), m.group(2))), budget_max=str(_money(m.group(3), m.group(4)))
            )
        else:
            m = re.search(r"(fixed[- ]price|budget)[^\n$\d]{0,20}" + _MONEY, text, re.I)
            if m:
                out.update(job_type="fixed", budget_max=str(_money(m.group(2), m.group(3))))
    lvl = re.search(r"\b(entry level|entry|intermediate|expert)\b", text, re.I)
    if lvl:
        out["experience_level"] = lvl.group(1).lower().replace(" level", "")
    url = re.search(r"https?://\S+", text)
    if url:
        out["url"] = url.group(0).rstrip(").,")
    return out


# --- CSV import --------------------------------------------------------------
CSV_COLUMNS = {
    "title",
    "description",
    "budget_min",
    "budget_max",
    "currency",
    "job_type",
    "required_skills",
    "experience_level",
    "url",
    "posted_at",
    "notes",
}


def _row_to_payload(row: dict[str, str]) -> dict[str, Any]:
    clean = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    payload: dict[str, Any] = {k: v for k, v in clean.items() if k in CSV_COLUMNS and v != ""}
    if "required_skills" in payload:
        payload["required_skills"] = [s for s in re.split(r"[;,|]", payload["required_skills"]) if s.strip()]
    for k in ("budget_min", "budget_max"):
        if k in payload:
            try:
                payload[k] = Decimal(payload[k].replace("$", "").replace(",", ""))
            except InvalidOperation:
                raise ValueError(f"{k} must be a number") from None
    if "posted_at" in payload:
        try:
            payload["posted_at"] = datetime.fromisoformat(payload["posted_at"])
        except ValueError:
            raise ValueError("posted_at must be an ISO date, e.g. 2026-01-31") from None
    return payload


def import_csv(db: Session, user_id: uuid.UUID, content: bytes, filename: str | None) -> JobImport:
    settings = get_settings()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("CSV must be UTF-8 encoded.", code="invalid_csv") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    if not {"title", "description"} <= headers:
        raise AppError(
            "CSV must include 'title' and 'description' columns.",
            code="invalid_csv",
            details={"supported_columns": sorted(CSV_COLUMNS)},
        )
    imp = JobImport(user_id=user_id, source="csv", filename=(filename or "")[:255] or None)
    db.add(imp)
    db.flush()
    errors: list[dict[str, Any]] = []
    for i, row in enumerate(reader, start=2):  # header is line 1
        if imp.total_rows >= settings.MAX_CSV_ROWS:
            errors.append({"line": i, "error": f"Row limit of {settings.MAX_CSV_ROWS} reached; remaining rows skipped."})
            break
        imp.total_rows += 1
        try:
            data = JobCreate.model_validate(_row_to_payload(row))
        except (ValidationError, ValueError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            errors.append({"line": i, "error": msg[:200]})
            continue
        with db.begin_nested():
            _job, created = create_job(db, user_id, data, source="csv", import_id=imp.id)
        if created:
            imp.created_count += 1
        else:
            imp.duplicate_count += 1
    imp.errors = errors[:100]
    imp.error_count = len(errors)
    db.commit()
    db.refresh(imp)
    return imp

"""Portfolio embedding lifecycle and semantic job-to-portfolio matching."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProvider
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import EmbeddingStatus, Job, PortfolioProject
from app.services.ai_runner import ai_embed
from app.services.skills import extract_skills_from_text, normalize_skills
from app.vector_store.factory import get_vector_store

log = get_logger(__name__)


def namespace_for(model: str) -> str:
    return f"portfolio__{model}"


def project_document(p: PortfolioProject) -> str:
    parts = [
        f"Project: {p.title}",
        f"Category: {p.category}" if p.category else "",
        f"Role: {p.role}" if p.role else "",
        f"Skills: {', '.join(p.skills)}" if p.skills else "",
        f"Description: {p.description}",
        f"Outcomes: {p.achievements}" if p.achievements else "",
    ]
    return "\n".join(x for x in parts if x).strip()


def job_document(job: Job) -> str:
    return "\n".join(
        x
        for x in [
            f"Job: {job.title}",
            f"Skills: {', '.join(job.required_skills)}" if job.required_skills else "",
            f"Description: {job.description[:6000]}",
        ]
        if x
    )


def content_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def index_projects(db: Session, provider: AIProvider, projects: list[PortfolioProject], *, force: bool = False) -> dict[str, int]:
    """Embed projects whose content changed (or that previously failed). Never raises for per-batch AI errors."""
    store = get_vector_store()
    model = provider.embedding_model
    todo: list[tuple[PortfolioProject, str, str]] = []
    skipped = 0
    for p in projects:
        doc = project_document(p)
        h = content_hash(model, doc)
        if not force and p.embedding_status == EmbeddingStatus.READY and p.embedding_hash == h:
            skipped += 1
            continue
        todo.append((p, doc, h))
    if not todo:
        return {"indexed": 0, "skipped": skipped, "failed": 0}
    user_id = todo[0][0].user_id
    try:
        result = ai_embed(db, provider, user_id=user_id, texts=[d for _, d, _ in todo], operation="embed_portfolio")
    except AppError as exc:
        for p, _, _ in todo:
            p.embedding_status = EmbeddingStatus.FAILED
            p.embedding_error = exc.message[:300]
        db.commit()
        return {"indexed": 0, "skipped": skipped, "failed": len(todo)}
    now = datetime.now(UTC)
    for (p, _, h), vec in zip(todo, result.vectors, strict=True):
        if p.embedding_model and p.embedding_model != model:
            store.delete(namespace=namespace_for(p.embedding_model), user_id=str(p.user_id), item_ids=[str(p.id)])
        store.upsert(namespace=namespace_for(model), user_id=str(p.user_id), item_id=str(p.id), vector=vec, content_hash=h)
        p.embedding_status = EmbeddingStatus.READY
        p.embedding_hash = h
        p.embedding_model = model
        p.embedding_error = None
        p.embedded_at = now
    db.commit()
    return {"indexed": len(todo), "skipped": skipped, "failed": 0}


def reindex_user(db: Session, provider: AIProvider, user_id: uuid.UUID, *, force: bool = False) -> dict[str, int]:
    projects = list(db.scalars(select(PortfolioProject).where(PortfolioProject.user_id == user_id)))
    return index_projects(db, provider, projects, force=force)


def remove_project_vectors(project: PortfolioProject) -> None:
    if project.embedding_model:
        get_vector_store().delete(
            namespace=namespace_for(project.embedding_model), user_id=str(project.user_id), item_ids=[str(project.id)]
        )


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _evidence(project: PortfolioProject, job_skills: list[str], job_text: str) -> dict[str, Any]:
    proj_skills = normalize_skills(project.skills + extract_skills_from_text(project.description))
    overlap = [s for s in proj_skills if s in job_skills]
    keywords = {w for w in re.findall(r"[a-z]{5,}", job_text.lower())}
    best: tuple[int, str] = (0, "")
    for sent in _SENT_SPLIT.split(project.description):
        hits = len({w for w in re.findall(r"[a-z]{5,}", sent.lower())} & keywords)
        if hits > best[0]:
            best = (hits, sent.strip())
    return {"shared_skills": overlap, "excerpt": best[1][:300] or project.description[:200]}


def match_portfolio(db: Session, provider: AIProvider, user_id: uuid.UUID, job: Job, *, top_k: int = 3) -> list[dict[str, Any]]:
    """Semantic retrieval of the user's most relevant projects for a job."""
    projects = list(db.scalars(select(PortfolioProject).where(PortfolioProject.user_id == user_id)))
    if not projects:
        return []
    index_projects(db, provider, projects)
    job_vec = ai_embed(db, provider, user_id=user_id, texts=[job_document(job)], operation="embed_job").vectors[0]
    hits = get_vector_store().query(
        namespace=namespace_for(provider.embedding_model), user_id=str(user_id), vector=job_vec, top_k=top_k * 2
    )
    # PostgreSQL is authoritative: only keep ids that belong to this user.
    owned = {str(p.id): p for p in projects}
    job_skills = normalize_skills(job.required_skills + extract_skills_from_text(job.description))
    out: list[dict[str, Any]] = []
    for hit in hits:
        p = owned.get(hit.item_id)
        if p is None:
            log.warning("vector_hit_not_owned_ignored")
            continue
        ev = _evidence(p, job_skills, job.description)
        out.append(
            {
                "project_id": str(p.id),
                "title": p.title,
                "similarity": max(0.0, min(1.0, hit.score)),
                "shared_skills": ev["shared_skills"],
                "evidence": ev["excerpt"],
                "url": p.url,
                "is_demo": p.is_demo,
            }
        )
        if len(out) >= top_k:
            break
    return out

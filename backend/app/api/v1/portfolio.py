from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import String, cast, or_, select

from app.ai.factory import get_ai_provider
from app.api.deps import AIUser, CurrentUser, DbSession
from app.core.errors import AppError
from app.models import PortfolioProject
from app.repositories.base import get_owned, paginate
from app.schemas.common import Message, Page
from app.schemas.profile import PortfolioIn, PortfolioOut
from app.services import portfolio_index

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _apply(project: PortfolioProject, body: PortfolioIn) -> None:
    data = body.model_dump()
    data["url"] = str(body.url) if body.url else None
    data["image_url"] = str(body.image_url) if body.image_url else None
    for k, v in data.items():
        setattr(project, k, v)


def _try_index(db: DbSession, project: PortfolioProject) -> None:
    """Embed immediately when AI is configured; otherwise leave status 'pending' for later reindexing."""
    try:
        provider = get_ai_provider(db)
    except AppError as exc:
        project.embedding_status = "pending"
        project.embedding_error = exc.message[:300]
        db.commit()
        return
    portfolio_index.index_projects(db, provider, [project])


@router.get("", response_model=Page[PortfolioOut])
def list_projects(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
    skill: str | None = Query(default=None, max_length=60),
    category: str | None = Query(default=None, max_length=100),
    sort: Literal["newest", "oldest", "title"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    stmt = select(PortfolioProject).where(PortfolioProject.user_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(PortfolioProject.title.ilike(like), PortfolioProject.description.ilike(like)))
    if skill:
        stmt = stmt.where(cast(PortfolioProject.skills, String).ilike(f"%{skill}%"))
    if category:
        stmt = stmt.where(PortfolioProject.category.ilike(category))
    order: Any = {
        "newest": PortfolioProject.created_at.desc(),
        "oldest": PortfolioProject.created_at.asc(),
        "title": PortfolioProject.title.asc(),
    }[sort]
    return paginate(db, stmt.order_by(order), page, page_size)


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def create_project(body: PortfolioIn, user: CurrentUser, db: DbSession) -> PortfolioProject:
    project = PortfolioProject(user_id=user.id, title=body.title, description=body.description)
    _apply(project, body)
    db.add(project)
    db.commit()
    _try_index(db, project)
    db.refresh(project)
    return project


@router.post("/reindex", response_model=dict)
def reindex(user: AIUser, db: DbSession, force: bool = False) -> dict:
    """Embed new/changed/failed projects (or all with ``force=true``). Unchanged projects are skipped."""
    provider = get_ai_provider(db)
    return portfolio_index.reindex_user(db, provider, user.id, force=force)


@router.get("/{project_id}", response_model=PortfolioOut)
def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PortfolioProject:
    return get_owned(db, PortfolioProject, project_id, user.id, "Portfolio project")


@router.put("/{project_id}", response_model=PortfolioOut)
def update_project(project_id: uuid.UUID, body: PortfolioIn, user: CurrentUser, db: DbSession) -> PortfolioProject:
    project = get_owned(db, PortfolioProject, project_id, user.id, "Portfolio project")
    _apply(project, body)
    project.is_demo = False
    db.commit()
    _try_index(db, project)  # re-embeds only if the content hash changed
    db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=Message)
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    project = get_owned(db, PortfolioProject, project_id, user.id, "Portfolio project")
    portfolio_index.remove_project_vectors(project)
    db.delete(project)
    db.commit()
    return Message(message="Project deleted.")

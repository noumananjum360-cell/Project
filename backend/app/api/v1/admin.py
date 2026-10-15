"""Administrative endpoints. Admins see account metadata and aggregates, never user content."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select, text

from app.ai.factory import ai_status
from app.api.deps import AdminUser, DbSession
from app.core.errors import AppError, NotFoundError
from app.db.session import engine
from app.models import AIUsageLog, AuditLog, Job, JobAnalysis, PortfolioProject, Proposal, Role, User
from app.repositories.base import paginate
from app.schemas.auth import UserOut
from app.services.audit import audit
from app.services.auth_service import revoke_all_sessions
from app.services.system_settings import get_setting, set_setting
from app.vector_store.factory import get_vector_store

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(USER|ADMIN)$")


class ScoringConfigIn(BaseModel):
    skills: float = Field(ge=0, le=100)
    portfolio: float = Field(ge=0, le=100)
    experience: float = Field(ge=0, le=100)
    budget: float = Field(ge=0, le=100)
    scope: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)
    strong: int = Field(default=75, ge=1, le=100)
    possible: int = Field(default=50, ge=0, le=99)
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    similarity_floor: float = Field(default=0.15, ge=-1, le=1)
    similarity_ceiling: float = Field(default=0.6, ge=-1, le=1)

    @model_validator(mode="after")
    def _check(self) -> ScoringConfigIn:
        total = self.skills + self.portfolio + self.experience + self.budget + self.scope + self.risk
        if abs(total - 100) > 0.01:
            raise ValueError(f"Weights must sum to 100 (currently {total}).")
        if self.possible >= self.strong:
            raise ValueError("'possible' threshold must be lower than 'strong'.")
        if self.similarity_floor >= self.similarity_ceiling:
            raise ValueError("similarity_floor must be lower than similarity_ceiling.")
        return self


class AIConfigIn(BaseModel):
    chat_model: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")
    embedding_model: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")
    timeout_seconds: float | None = Field(default=None, ge=5, le=300)


class UsageLimitsIn(BaseModel):
    daily_ai_requests_per_user: int = Field(ge=0, le=100000, description="0 disables the limit")


@router.get("/users")
def list_users(
    _admin: AdminUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    stmt = select(User)
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    result = paginate(db, stmt.order_by(User.created_at.desc()), page, page_size)
    result["items"] = [UserOut.model_validate(u).model_dump() | {"last_login_at": u.last_login_at} for u in result["items"]]
    return result


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: AdminUserUpdate, admin: AdminUser, db: DbSession, request: Request) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == admin.id and (body.is_active is False or body.role == Role.USER):
        raise AppError("You cannot deactivate or demote your own account.", code="self_modification")
    changes: dict[str, object] = {}
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            revoke_all_sessions(db, user.id)
    if body.role is not None and body.role != user.role:
        user.role = body.role
        changes["role"] = body.role
    if changes:
        audit(
            db, "admin.user_updated", actor_id=admin.id, target_type="user", target_id=user.id, request=request, details=changes
        )
    db.commit()
    return UserOut.model_validate(user).model_dump()


@router.get("/usage")
def usage(_admin: AdminUser, db: DbSession, days: int = Query(default=30, ge=1, le=365)) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    by_op = db.execute(
        select(
            AIUsageLog.operation,
            AIUsageLog.provider,
            AIUsageLog.model,
            func.count(),
            func.sum(case_success()),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.sum(AIUsageLog.estimated_cost),
        )
        .where(AIUsageLog.created_at >= since)
        .group_by(AIUsageLog.operation, AIUsageLog.provider, AIUsageLog.model)
    ).all()
    errors = db.execute(
        select(AIUsageLog.error_code, func.count())
        .where(AIUsageLog.created_at >= since, AIUsageLog.success.is_(False))
        .group_by(AIUsageLog.error_code)
    ).all()
    return {
        "days": days,
        "totals": {
            "users": db.scalar(select(func.count()).select_from(User)),
            "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))),
            "jobs": db.scalar(select(func.count()).select_from(Job)),
            "analyses": db.scalar(select(func.count()).select_from(JobAnalysis)),
            "proposals": db.scalar(select(func.count()).select_from(Proposal)),
            "portfolio_projects": db.scalar(select(func.count()).select_from(PortfolioProject)),
        },
        "ai_by_operation": [
            {
                "operation": r[0],
                "provider": r[1],
                "model": r[2],
                "requests": r[3],
                "successes": int(r[4] or 0),
                "input_tokens": int(r[5]),
                "output_tokens": int(r[6]),
                "estimated_cost": float(r[7]) if r[7] is not None else None,
            }
            for r in by_op
        ],
        "ai_errors": [{"error_code": e or "unknown", "count": c} for e, c in errors],
        "usage_limits": get_setting(db, "usage_limits"),
    }


def case_success():  # type: ignore[no-untyped-def]
    from sqlalchemy import case

    return case((AIUsageLog.success.is_(True), 1), else_=0)


@router.get("/health")
def health(_admin: AdminUser, db: DbSession) -> dict:
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    try:
        store = get_vector_store()
        vec = {"backend": store.backend, "healthy": store.healthy()}
    except Exception as exc:  # noqa: BLE001
        vec = {"backend": "unavailable", "healthy": False, "error": type(exc).__name__}
    since = datetime.now(UTC) - timedelta(hours=24)
    recent_failures = db.scalar(
        select(func.count()).select_from(AIUsageLog).where(AIUsageLog.created_at >= since, AIUsageLog.success.is_(False))
    )
    pool = engine.pool
    return {
        "database": {"healthy": db_ok, "pool_status": pool.status() if hasattr(pool, "status") else None},
        "vector_store": vec,
        "ai": ai_status(db),
        "ai_failures_24h": recent_failures,
        "pending_embeddings": db.scalar(
            select(func.count()).select_from(PortfolioProject).where(PortfolioProject.embedding_status != "ready")
        ),
    }


@router.get("/scoring-config")
def get_scoring_config(_admin: AdminUser, db: DbSession) -> dict:
    return {"weights": get_setting(db, "scoring_weights"), "thresholds": get_setting(db, "scoring_thresholds")}


@router.put("/scoring-config")
def put_scoring_config(body: ScoringConfigIn, admin: AdminUser, db: DbSession, request: Request) -> dict:
    data = body.model_dump()
    weights = {k: data[k] for k in ("skills", "portfolio", "experience", "budget", "scope", "risk")}
    thresholds = {k: data[k] for k in ("strong", "possible", "min_confidence", "similarity_floor", "similarity_ceiling")}
    set_setting(db, "scoring_weights", weights, admin.id)
    set_setting(db, "scoring_thresholds", thresholds, admin.id)
    audit(
        db,
        "admin.scoring_config_updated",
        actor_id=admin.id,
        target_type="system_setting",
        target_id="scoring",
        request=request,
        details={"weights": weights, "thresholds": thresholds},
    )
    db.commit()
    return {"weights": weights, "thresholds": thresholds}


@router.get("/ai-config")
def get_ai_config(_admin: AdminUser, db: DbSession) -> dict:
    """Non-secret AI settings. API keys are never returned."""
    return {"overrides": get_setting(db, "ai_config"), "status": ai_status(db)}


@router.put("/ai-config")
def put_ai_config(body: AIConfigIn, admin: AdminUser, db: DbSession, request: Request) -> dict:
    value = set_setting(db, "ai_config", body.model_dump(), admin.id)
    audit(
        db,
        "admin.ai_config_updated",
        actor_id=admin.id,
        target_type="system_setting",
        target_id="ai_config",
        request=request,
        details=body.model_dump(),
    )
    db.commit()
    return {"overrides": value, "status": ai_status(db)}


@router.put("/usage-limits")
def put_usage_limits(body: UsageLimitsIn, admin: AdminUser, db: DbSession, request: Request) -> dict:
    value = set_setting(db, "usage_limits", body.model_dump(), admin.id)
    audit(
        db,
        "admin.usage_limits_updated",
        actor_id=admin.id,
        target_type="system_setting",
        target_id="usage_limits",
        request=request,
        details=body.model_dump(),
    )
    db.commit()
    return value


@router.get("/audit-logs")
def audit_logs(
    _admin: AdminUser,
    db: DbSession,
    action: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    result = paginate(db, stmt.order_by(AuditLog.created_at.desc()), page, page_size)
    result["items"] = [
        {
            "id": a.id,
            "actor_user_id": a.actor_user_id,
            "action": a.action,
            "target_type": a.target_type,
            "target_id": a.target_id,
            "ip_address": a.ip_address,
            "details": a.details,
            "created_at": a.created_at,
        }
        for a in result["items"]
    ]
    return result

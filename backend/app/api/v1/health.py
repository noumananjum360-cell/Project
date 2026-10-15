from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.ai.factory import ai_status
from app.api.deps import DbSession
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: DbSession) -> JSONResponse:
    """Readiness probe: database connectivity plus public, non-secret AI configuration status."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    s = get_settings()
    status = ai_status(db) if db_ok else {}
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "environment": s.ENVIRONMENT,
        "ai_configured": status.get("configured", False),
        "ai_simulated": status.get("simulated", False),
        "demo_mode": s.DEMO_MODE,
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)

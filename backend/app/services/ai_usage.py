"""AI usage accounting: per-user limits, token logging and cost estimation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import Usage
from app.core.config import get_settings
from app.core.errors import UsageLimitError
from app.models import AIUsageLog
from app.services.system_settings import get_setting


def estimate_cost(model: str | None, usage: Usage) -> Decimal | None:
    """Return an estimated USD cost, or None when pricing for the model is unknown."""
    if not model:
        return None
    pricing = get_settings().ai_pricing.get(model)
    if not pricing:
        return None
    try:
        cost = Decimal(str(pricing.get("input_per_1m", 0))) * Decimal(usage.input_tokens or 0) / Decimal(1_000_000)
        cost += Decimal(str(pricing.get("output_per_1m", 0))) * Decimal(usage.output_tokens or 0) / Decimal(1_000_000)
    except (ArithmeticError, ValueError):
        return None
    return cost.quantize(Decimal("0.000001"))


def check_usage_limit(db: Session, user_id: uuid.UUID) -> None:
    limit = int(get_setting(db, "usage_limits").get("daily_ai_requests_per_user") or 0)
    if limit <= 0:
        return
    since = datetime.now(UTC) - timedelta(days=1)
    used = db.scalar(
        select(func.count()).select_from(AIUsageLog).where(AIUsageLog.user_id == user_id, AIUsageLog.created_at >= since)
    )
    if (used or 0) >= limit:
        raise UsageLimitError("You have reached the daily AI usage limit. Please try again later.", details={"limit": limit})


def log_usage(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    operation: str,
    provider: str,
    model: str | None,
    usage: Usage | None,
    success: bool,
    is_simulated: bool,
    error_code: str | None = None,
) -> Decimal | None:
    usage = usage or Usage()
    cost = estimate_cost(model, usage) if success else None
    db.add(
        AIUsageLog(
            user_id=user_id,
            operation=operation,
            provider=provider,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=cost,
            latency_ms=usage.latency_ms,
            success=success,
            error_code=error_code,
            is_simulated=is_simulated,
        )
    )
    return cost

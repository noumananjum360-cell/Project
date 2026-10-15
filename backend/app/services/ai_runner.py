"""Wraps provider calls with usage limits, logging and cost estimation."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.base import AIProvider, CompletionResult, EmbeddingResult, TModel
from app.core.errors import AppError
from app.services.ai_usage import check_usage_limit, log_usage


def ai_complete(
    db: Session,
    provider: AIProvider,
    *,
    user_id: uuid.UUID | None,
    operation: str,
    system: str,
    user: str,
    schema: type[TModel],
    temperature: float = 0.3,
) -> tuple[CompletionResult[TModel], Decimal | None]:
    if user_id is not None:
        check_usage_limit(db, user_id)
    try:
        result = provider.complete_structured(
            system=system, user=user, schema=schema, operation=operation, temperature=temperature
        )
    except AppError as exc:
        log_usage(
            db,
            user_id=user_id,
            operation=operation,
            provider=provider.name,
            model=provider.chat_model,
            usage=None,
            success=False,
            is_simulated=provider.is_simulated,
            error_code=exc.code,
        )
        db.commit()
        raise
    cost = log_usage(
        db,
        user_id=user_id,
        operation=operation,
        provider=result.provider,
        model=result.model,
        usage=result.usage,
        success=True,
        is_simulated=result.is_simulated,
    )
    return result, cost


def ai_embed(
    db: Session, provider: AIProvider, *, user_id: uuid.UUID | None, texts: list[str], operation: str = "embedding"
) -> EmbeddingResult:
    try:
        result = provider.embed(texts)
    except AppError as exc:
        log_usage(
            db,
            user_id=user_id,
            operation=operation,
            provider=provider.name,
            model=provider.embedding_model,
            usage=None,
            success=False,
            is_simulated=provider.is_simulated,
            error_code=exc.code,
        )
        db.commit()
        raise
    log_usage(
        db,
        user_id=user_id,
        operation=operation,
        provider=result.provider,
        model=result.model,
        usage=result.usage,
        success=True,
        is_simulated=result.is_simulated,
    )
    return result

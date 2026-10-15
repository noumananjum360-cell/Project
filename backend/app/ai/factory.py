"""Select the configured AI provider. Production never falls back to the mock."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import AIProvider
from app.ai.mock_provider import MockProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import get_settings
from app.core.errors import AIUnavailableError
from app.services.system_settings import get_setting

# Test hook: allows tests to inject a provider (e.g. a failing one).
_override: AIProvider | None = None


def set_provider_override(provider: AIProvider | None) -> None:
    global _override
    _override = provider


def ai_status(db: Session | None = None) -> dict[str, Any]:
    s = get_settings()
    overrides = get_setting(db, "ai_config") if db is not None else {}
    provider = s.AI_PROVIDER
    configured = provider == "mock" and s.mock_ai_allowed or provider != "mock" and bool(s.OPENAI_API_KEY)
    if provider == "openai_compatible" and not s.OPENAI_BASE_URL:
        configured = False
    return {
        "provider": provider,
        "configured": configured,
        "simulated": provider == "mock",
        "demo_mode": s.DEMO_MODE,
        "chat_model": overrides.get("chat_model") or (MockProvider.chat_model if provider == "mock" else s.OPENAI_MODEL),
        "embedding_model": overrides.get("embedding_model")
        or (MockProvider.embedding_model if provider == "mock" else s.OPENAI_EMBEDDING_MODEL),
    }


def get_ai_provider(db: Session | None = None) -> AIProvider:
    if _override is not None:
        return _override
    s = get_settings()
    if s.AI_PROVIDER == "mock":
        if not s.mock_ai_allowed:
            raise AIUnavailableError(
                "The simulated AI provider is only available in test or demo mode. Configure a real AI provider.",
                code="ai_not_configured",
            )
        return MockProvider()
    if not s.OPENAI_API_KEY:
        raise AIUnavailableError(
            "AI features are not configured. Set OPENAI_API_KEY (and AI_PROVIDER) on the server to enable them.",
            code="ai_not_configured",
        )
    if s.AI_PROVIDER == "openai_compatible" and not s.OPENAI_BASE_URL:
        raise AIUnavailableError("AI_PROVIDER=openai_compatible requires OPENAI_BASE_URL.", code="ai_not_configured")
    overrides = get_setting(db, "ai_config") if db is not None else {}
    return OpenAIProvider(
        api_key=s.OPENAI_API_KEY,
        base_url=s.OPENAI_BASE_URL,
        chat_model=overrides.get("chat_model") or s.OPENAI_MODEL,
        embedding_model=overrides.get("embedding_model") or s.OPENAI_EMBEDDING_MODEL,
        timeout=float(overrides.get("timeout_seconds") or s.AI_REQUEST_TIMEOUT_SECONDS),
        max_retries=s.AI_MAX_RETRIES,
        name="openai" if s.AI_PROVIDER == "openai" else "openai_compatible",
    )

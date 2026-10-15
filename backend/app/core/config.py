"""Application settings loaded from environment variables.

Every setting has a safe development default except secrets, which must be
provided explicitly in production (validated in ``Settings.validate_for_runtime``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
AIProviderName = Literal["openai", "openai_compatible", "mock"]

_INSECURE_DEV_SECRET = "dev-insecure-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core -------------------------------------------------------------
    ENVIRONMENT: Environment = "development"
    APP_NAME: str = "BidGenie AI"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    DATABASE_URL: str = "postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie"

    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"
    # Comma-separated list of additional allowed CORS origins
    # (e.g. chrome-extension://<extension-id>).
    CORS_EXTRA_ORIGINS: str = ""

    # --- Auth -------------------------------------------------------------
    JWT_SECRET_KEY: str = _INSECURE_DEV_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 48
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_DOMAIN: str | None = None

    # --- Rate limits (requests per window) -------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_AI_PER_MINUTE: int = 20

    # --- Email (optional) -------------------------------------------------
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "BidGenie AI <no-reply@bidgenie.local>"
    SMTP_STARTTLS: bool = True

    # --- AI ---------------------------------------------------------------
    AI_PROVIDER: AIProviderName = "openai"
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None  # for openai_compatible providers
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_REQUEST_TIMEOUT_SECONDS: float = 60.0
    AI_MAX_RETRIES: int = 2
    # JSON: {"model-name": {"input_per_1m": 0.15, "output_per_1m": 0.6}}
    AI_PRICING_JSON: str = "{}"
    # Demo mode: allows the deterministic mock provider outside of tests and
    # labels every AI result as simulated. Never allowed in production.
    DEMO_MODE: bool = False

    # --- Vector store -----------------------------------------------------
    VECTOR_STORE: Literal["chroma", "faiss", "memory"] = "chroma"
    CHROMA_PERSIST_DIRECTORY: str = "./data/chroma"
    FAISS_INDEX_DIRECTORY: str = "./data/faiss"

    # --- Uploads ----------------------------------------------------------
    UPLOAD_DIRECTORY: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 5
    RESUME_RETAIN_FILES: bool = False

    # --- Bootstrap ----------------------------------------------------------
    MAX_CSV_ROWS: int = 500

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    # ---------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.FRONTEND_URL.rstrip("/")}
        for item in self.CORS_EXTRA_ORIGINS.split(","):
            if item.strip():
                origins.add(item.strip().rstrip("/"))
        return sorted(origins)

    @property
    def ai_pricing(self) -> dict[str, dict[str, float]]:
        try:
            data = json.loads(self.AI_PRICING_JSON or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @property
    def mock_ai_allowed(self) -> bool:
        return self.ENVIRONMENT == "test" or (self.DEMO_MODE and not self.is_production)

    def validate_for_runtime(self) -> None:
        """Fail fast on dangerous production configuration."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.JWT_SECRET_KEY == _INSECURE_DEV_SECRET or len(self.JWT_SECRET_KEY) < 32:
            problems.append("JWT_SECRET_KEY must be set to a random value of at least 32 characters")
        if not self.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true in production")
        if self.DEMO_MODE:
            problems.append("DEMO_MODE cannot be enabled in production")
        if self.AI_PROVIDER == "mock":
            problems.append("AI_PROVIDER=mock is not allowed in production")
        if not self.FRONTEND_URL.startswith("https://"):
            problems.append("FRONTEND_URL must use https in production")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()

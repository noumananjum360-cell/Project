from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel, SkillList
from app.schemas.profile import Length, Tone

JobType = Literal["hourly", "fixed", "unknown"]
ExperienceLevel = Literal["entry", "intermediate", "expert", "unknown"]
JobStatus = Literal["new", "saved", "shortlisted", "applied", "skipped", "archived"]


class ClientInfo(BaseModel):
    """Client details from an authorised source or entered by the user."""

    country: str | None = Field(default=None, max_length=100)
    payment_verified: bool | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    total_spent: str | None = Field(default=None, max_length=50)
    hire_rate: str | None = Field(default=None, max_length=50)
    jobs_posted: int | None = Field(default=None, ge=0)


class JobBase(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=20, max_length=20000)
    budget_min: Decimal | None = Field(default=None, ge=0, le=10_000_000, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, le=10_000_000, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    job_type: JobType = "unknown"
    required_skills: SkillList = Field(default_factory=list, max_length=40)
    experience_level: ExperienceLevel = "unknown"
    client_info: ClientInfo | None = None
    proposals_info: str | None = Field(default=None, max_length=200)
    posted_at: datetime | None = None
    url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _budget(self) -> JobBase:
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class JobCreate(JobBase):
    pass


class JobExtensionCreate(JobBase):
    """Job details extracted by the browser extension from the visible page, after user action."""

    source_page: str | None = Field(default=None, max_length=1000)


class JobUpdate(JobBase):
    status: JobStatus = "new"


class JobStatusUpdate(BaseModel):
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


class JobOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str
    budget_min: Decimal | None
    budget_max: Decimal | None
    currency: str
    job_type: str
    required_skills: list[str]
    experience_level: str
    client_info: dict[str, Any]
    proposals_info: str | None
    posted_at: datetime | None
    url: str | None
    source: str
    is_demo: bool
    status: str
    notes: str | None
    latest_fit_score: int | None
    latest_recommendation: str | None
    analyzed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ParseTextIn(BaseModel):
    text: str = Field(min_length=20, max_length=20000)


class JobImportOut(ORMModel):
    id: uuid.UUID
    source: str
    filename: str | None
    total_rows: int
    created_count: int
    duplicate_count: int
    error_count: int
    errors: list[dict[str, Any]]
    created_at: datetime


class AnalysisOut(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    fit_score: int
    score_confidence: float
    recommendation: str
    result: dict[str, Any]
    weights: dict[str, Any]
    scoring_version: str
    provider: str
    model: str | None
    embedding_model: str | None
    profile_version: int | None
    is_simulated: bool
    created_at: datetime
    profile_changed_since: bool = False


class PortfolioMatchOut(BaseModel):
    project_id: str
    title: str
    similarity: float
    shared_skills: list[str]
    evidence: str
    url: str | None
    is_demo: bool


class ProposalGenerateIn(BaseModel):
    job_id: uuid.UUID
    tone: Tone | None = None
    length: Length | None = None
    emphasize_skills: SkillList = Field(default_factory=list, max_length=10)
    project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    custom_opening: str | None = Field(default=None, max_length=600)
    exclude: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("exclude")
    @classmethod
    def _exclude(cls, v: list[str]) -> list[str]:
        return [x.strip()[:100] for x in v if x.strip()]

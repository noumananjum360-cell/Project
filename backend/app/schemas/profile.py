from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.schemas.common import ORMModel, ShortList, SkillList

Tone = Literal["professional", "friendly", "confident", "concise", "technical"]
Length = Literal["short", "standard", "detailed"]


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    overview: str | None = Field(default=None, max_length=5000)
    primary_skills: SkillList = Field(default_factory=list, max_length=40)
    additional_skills: SkillList = Field(default_factory=list, max_length=60)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    hourly_rate: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    preferred_categories: ShortList = Field(default_factory=list)
    preferred_project_types: ShortList = Field(default_factory=list)
    min_budget: Decimal | None = Field(default=None, ge=0, le=10_000_000, decimal_places=2)
    preferred_client_traits: ShortList = Field(default_factory=list)
    proposal_tone: Tone = "professional"
    proposal_length: Length = "standard"
    languages: ShortList = Field(default_factory=list)
    timezone: str | None = Field(default=None, max_length=64)
    availability: str | None = Field(default=None, max_length=300)


class ProfileOut(ORMModel):
    full_name: str | None
    headline: str | None
    overview: str | None
    primary_skills: list[str]
    additional_skills: list[str]
    years_experience: int | None
    hourly_rate: Decimal | None
    currency: str
    preferred_categories: list[str]
    preferred_project_types: list[str]
    min_budget: Decimal | None
    preferred_client_traits: list[str]
    proposal_tone: str
    proposal_length: str
    languages: list[str]
    timezone: str | None
    availability: str | None
    profile_version: int
    is_demo: bool
    updated_at: datetime


class PreferencesIn(BaseModel):
    fit_score_threshold: int = Field(ge=0, le=100)
    auto_analyze_on_import: bool
    notify_high_fit_jobs: bool
    notify_follow_ups: bool


class PreferencesOut(ORMModel):
    fit_score_threshold: int
    auto_analyze_on_import: bool
    notify_high_fit_jobs: bool
    notify_follow_ups: bool


class ResumeOut(ORMModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None
    extracted_data: dict[str, Any] | None
    extraction_method: str | None
    is_simulated: bool
    file_retained: bool = False
    applied_at: datetime | None
    created_at: datetime


class ResumeApplyIn(BaseModel):
    """Fields the user confirmed from the extraction review screen."""

    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    overview: str | None = Field(default=None, max_length=5000)
    add_primary_skills: SkillList = Field(default_factory=list)
    add_additional_skills: SkillList = Field(default_factory=list)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    languages: SkillList = Field(default_factory=list)


class PortfolioIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=10, max_length=8000)
    skills: SkillList = Field(default_factory=list, max_length=40)
    category: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=200)
    achievements: str | None = Field(default=None, max_length=3000)
    url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_text: str | None = Field(default=None, max_length=100)

    @field_validator("end_date")
    @classmethod
    def _dates(cls, v: date | None, info: Any) -> date | None:
        start = info.data.get("start_date")
        if v and start and v < start:
            raise ValueError("End date must be after start date.")
        return v


class PortfolioOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str
    skills: list[str]
    category: str | None
    role: str | None
    achievements: str | None
    url: str | None
    image_url: str | None
    start_date: date | None
    end_date: date | None
    duration_text: str | None
    is_demo: bool
    embedding_status: str
    embedding_error: str | None
    embedded_at: datetime | None
    created_at: datetime
    updated_at: datetime

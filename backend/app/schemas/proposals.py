from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, SkillList
from app.schemas.profile import Length, Tone

Section = Literal["hook", "solution", "proof", "call_to_action"]
AppStatus = Literal["draft", "ready", "sent", "interview", "hired", "declined", "archived"]


class ProposalOut(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    title: str
    content: str
    sections: dict[str, str]
    tone: str
    length: str
    options: dict[str, Any]
    current_version_number: int
    warnings: list[str]
    is_simulated: bool
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class ProposalListItem(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    title: str
    tone: str
    length: str
    current_version_number: int
    is_simulated: bool
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    job_title: str | None = None
    application_status: str | None = None


class ProposalUpdate(BaseModel):
    """Autosave/edit. ``content`` is authoritative; ``sections`` optional."""

    title: str | None = Field(default=None, max_length=300)
    content: str = Field(min_length=1, max_length=20000)
    sections: dict[Section, str] | None = None


class ProposalRegenerateIn(BaseModel):
    section: Section | None = None
    tone: Tone | None = None
    length: Length | None = None
    emphasize_skills: SkillList = Field(default_factory=list, max_length=10)
    project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    custom_opening: str | None = Field(default=None, max_length=600)
    exclude: list[str] = Field(default_factory=list, max_length=10)


class ProposalVersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    content: str
    sections: dict[str, str]
    source: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: Decimal | None
    used_project_ids: list[str]
    warnings: list[str]
    is_simulated: bool
    created_at: datetime


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    proposal_id: uuid.UUID | None = None
    status: AppStatus = "draft"
    notes: str | None = Field(default=None, max_length=5000)
    follow_up_at: datetime | None = None


class ApplicationUpdate(BaseModel):
    status: AppStatus | None = None
    proposal_id: uuid.UUID | None = None
    submitted_at: datetime | None = None
    interview_at: datetime | None = None
    contract_value: Decimal | None = Field(default=None, ge=0, le=100_000_000, decimal_places=2)
    contract_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    follow_up_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)
    status_note: str | None = Field(default=None, max_length=500)


class StatusHistoryOut(ORMModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class ApplicationOut(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    proposal_id: uuid.UUID | None
    proposal_version_number: int | None
    status: str
    submitted_at: datetime | None
    interview_at: datetime | None
    contract_value: Decimal | None
    contract_currency: str
    follow_up_at: datetime | None
    notes: str | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    job_title: str | None = None
    job_fit_score: int | None = None
    history: list[StatusHistoryOut] = Field(default_factory=list)


class NotificationOut(ORMModel):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime

"""Structured output contracts for every LLM operation (validated with Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExperienceItem(BaseModel):
    title: str = Field(max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=100)
    summary: str | None = Field(default=None, max_length=1000)


class ResumeExtraction(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    overview: str | None = Field(default=None, max_length=3000)
    skills: list[str] = Field(default_factory=list, max_length=80)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    languages: list[str] = Field(default_factory=list, max_length=20)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=30)
    education: list[str] = Field(default_factory=list, max_length=20)
    certifications: list[str] = Field(default_factory=list, max_length=30)


class AIRedFlag(BaseModel):
    flag: str = Field(max_length=200)
    evidence: str = Field(max_length=500)
    severity: Literal["low", "medium", "high"] = "low"


class AnalysisNarrative(BaseModel):
    explanation: str = Field(max_length=3000)
    feasibility_assessment: str = Field(max_length=1500)
    relevant_experience: list[str] = Field(default_factory=list, max_length=10)
    additional_red_flags: list[AIRedFlag] = Field(default_factory=list, max_length=10)
    positive_signals: list[str] = Field(default_factory=list, max_length=10)
    suggested_next_steps: list[str] = Field(default_factory=list, max_length=8)


class ProposalDraft(BaseModel):
    hook: str = Field(min_length=1, max_length=1500)
    solution: str = Field(min_length=1, max_length=4000)
    proof: str = Field(min_length=1, max_length=3000)
    call_to_action: str = Field(min_length=1, max_length=1000)
    used_project_ids: list[str] = Field(default_factory=list, max_length=5)


class SectionRewrite(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

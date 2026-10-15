"""Proposal generation, section regeneration, factuality checks and versioning."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.base import AIProvider, CompletionResult
from app.ai.schemas import ProposalDraft, SectionRewrite
from app.core.errors import AppError, NotFoundError
from app.models import Job, JobAnalysis, PortfolioProject, Proposal, ProposalVersion, User, UserProfile
from app.services.ai_runner import ai_complete
from app.services.analysis_service import job_dict, profile_dict
from app.services.portfolio_index import match_portfolio

SECTIONS = ("hook", "solution", "proof", "call_to_action")
_NUM_RE = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|k\b|x\b)?", re.I)


def assemble(sections: dict[str, str]) -> str:
    return "\n\n".join(sections[s].strip() for s in SECTIONS if sections.get(s, "").strip())


def find_unverified_figures(text: str, evidence_text: str) -> list[str]:
    """Numbers in the proposal that do not appear anywhere in the supplied evidence."""
    evidence_nums = {re.sub(r"[^\d.]", "", m.group(0)) for m in _NUM_RE.finditer(evidence_text)}
    flagged: list[str] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"[^\d.]", "", raw)
        if digits and digits not in evidence_nums and raw not in flagged:
            flagged.append(raw)
    return flagged


def _evidence_payload(
    db: Session, provider: AIProvider, user: User, job: Job, project_ids: list[uuid.UUID] | None
) -> tuple[dict[str, Any], list[PortfolioProject], list[str]]:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    prof = profile_dict(profile)
    if project_ids:
        projects = list(
            db.scalars(select(PortfolioProject).where(PortfolioProject.user_id == user.id, PortfolioProject.id.in_(project_ids)))
        )
        if len(projects) != len(set(project_ids)):
            raise NotFoundError("One or more selected portfolio projects were not found.")
    else:
        matches = match_portfolio(db, provider, user.id, job, top_k=3)
        ids = [uuid.UUID(m["project_id"]) for m in matches]
        found = {p.id: p for p in db.scalars(select(PortfolioProject).where(PortfolioProject.id.in_(ids)))} if ids else {}
        projects = [found[i] for i in ids if i in found and found[i].user_id == user.id]
    analysis = db.scalar(
        select(JobAnalysis)
        .where(JobAnalysis.job_id == job.id, JobAnalysis.user_id == user.id)
        .order_by(JobAnalysis.created_at.desc())
        .limit(1)
    )
    matched = analysis.result.get("matched_skills", []) if analysis else []
    project_payload = [
        {
            "id": str(p.id),
            "title": p.title,
            "description": p.description[:1500],
            "skills": p.skills,
            "role": p.role,
            "verified_outcomes": p.achievements,
            "url": p.url,
        }
        for p in projects
    ]
    payload = {
        "job": {k: v for k, v in job_dict(job).items() if k != "client_info"},
        "profile": {
            "name": prof.get("full_name"),
            "headline": prof.get("headline"),
            "overview": prof.get("overview"),
            "skills": (prof.get("primary_skills") or []) + (prof.get("additional_skills") or []),
            "years_experience": prof.get("years_experience"),
        },
        "portfolio_projects": project_payload,
        "matched_skills": matched,
    }
    return payload, projects, matched


def _evidence_text(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)


def _validate_draft(
    draft: ProposalDraft, payload: dict[str, Any], exclude: list[str]
) -> tuple[dict[str, str], list[str], list[str]]:
    allowed = {p["id"] for p in payload["portfolio_projects"]}
    used = [i for i in draft.used_project_ids if i in allowed]
    sections = {s: getattr(draft, s).strip() for s in SECTIONS}
    warnings: list[str] = []
    if len(used) != len(draft.used_project_ids):
        warnings.append("The AI referenced portfolio items that were not supplied; those references were ignored.")
    figures = find_unverified_figures(assemble(sections), _evidence_text(payload))
    if figures:
        warnings.append(
            "Review these figures — they do not appear in your profile, portfolio or the job post: " + ", ".join(figures[:8])
        )
    for term in exclude:
        if term and term.lower() in assemble(sections).lower():
            warnings.append(f"The draft mentions “{term}”, which you asked to exclude. Please edit it out.")
    return sections, used, warnings


def _record_version(
    db: Session,
    proposal: Proposal,
    *,
    source: str,
    result: CompletionResult[Any] | None,
    cost: Decimal | None,
    used: list[str],
    warnings: list[str],
) -> ProposalVersion:
    next_no = (
        db.scalar(select(func.max(ProposalVersion.version_number)).where(ProposalVersion.proposal_id == proposal.id)) or 0
    ) + 1
    v = ProposalVersion(
        proposal_id=proposal.id,
        user_id=proposal.user_id,
        version_number=next_no,
        content=proposal.content,
        sections=dict(proposal.sections),
        source=source,
        provider=result.provider if result else None,
        model=result.model if result else None,
        prompt_version=prompts.PROPOSAL_PROMPT_VERSION if result else None,
        input_tokens=result.usage.input_tokens if result else None,
        output_tokens=result.usage.output_tokens if result else None,
        estimated_cost=cost,
        used_project_ids=used,
        warnings=warnings,
        is_simulated=result.is_simulated if result else False,
    )
    db.add(v)
    proposal.current_version_number = next_no
    return v


def _generate_draft(
    db: Session, provider: AIProvider, user: User, job: Job, options: dict[str, Any]
) -> tuple[dict[str, str], list[str], list[str], CompletionResult[ProposalDraft], Decimal | None]:
    ids = [uuid.UUID(str(i)) for i in options.get("project_ids") or []]
    payload, _projects, _matched = _evidence_payload(db, provider, user, job, ids or None)
    if options.get("emphasize_skills"):
        payload["emphasize_skills"] = options["emphasize_skills"]
    if options.get("custom_opening"):
        payload["custom_opening"] = options["custom_opening"]
        payload["instruction_for_hook"] = "Use the freelancer's custom_opening as the start of the hook."
    if options.get("exclude"):
        payload["do_not_mention"] = options["exclude"]
    result, cost = ai_complete(
        db,
        provider,
        user_id=user.id,
        operation="proposal_generate",
        system=prompts.PROPOSAL_SYSTEM,
        user=prompts.proposal_user(payload, options["tone"], options["length"]),
        schema=ProposalDraft,
        temperature=0.5,
    )
    sections, used, warnings = _validate_draft(result.data, payload, options.get("exclude") or [])
    if options.get("custom_opening") and not sections["hook"].startswith(options["custom_opening"][:20]):
        sections["hook"] = f"{options['custom_opening'].strip()} {sections['hook']}".strip()
    return sections, used, warnings, result, cost


def generate_proposal(db: Session, provider: AIProvider, user: User, job: Job, options: dict[str, Any]) -> Proposal:
    sections, used, warnings, result, cost = _generate_draft(db, provider, user, job, options)
    proposal = Proposal(
        user_id=user.id,
        job_id=job.id,
        title=f"Proposal: {job.title[:280]}",
        content=assemble(sections),
        sections=sections,
        tone=options["tone"],
        length=options["length"],
        options={k: v for k, v in options.items() if k not in {"tone", "length"}},
        warnings=warnings,
        is_simulated=result.is_simulated,
    )
    db.add(proposal)
    db.flush()
    _record_version(db, proposal, source="generated", result=result, cost=cost, used=used, warnings=warnings)
    db.commit()
    db.refresh(proposal)
    return proposal


def regenerate_proposal(
    db: Session, provider: AIProvider, user: User, proposal: Proposal, options: dict[str, Any], section: str | None
) -> Proposal:
    job = db.scalar(select(Job).where(Job.id == proposal.job_id, Job.user_id == user.id))
    if job is None:
        raise NotFoundError("The job for this proposal no longer exists.")
    if section is None:
        sections, used, warnings, result, cost = _generate_draft(db, provider, user, job, options)
        source = "regenerated"
    else:
        payload, _projects, _ = _evidence_payload(
            db, provider, user, job, [uuid.UUID(str(i)) for i in options.get("project_ids") or []] or None
        )
        payload.update(
            {
                "section": section,
                "current_text": proposal.sections.get(section, ""),
                "other_sections": {k: v for k, v in proposal.sections.items() if k != section},
            }
        )
        sec_result, cost = ai_complete(
            db,
            provider,
            user_id=user.id,
            operation="proposal_section",
            system=prompts.SECTION_SYSTEM,
            user=prompts.section_user(payload, options["tone"]),
            schema=SectionRewrite,
            temperature=0.6,
        )
        sections = {**proposal.sections, section: sec_result.data.text.strip()}
        used = []
        figures = find_unverified_figures(sec_result.data.text, _evidence_text(payload))
        warnings = (
            ["Review these figures — they do not appear in your supplied evidence: " + ", ".join(figures[:8])] if figures else []
        )
        source = "section_regenerated"
        result = sec_result  # type: ignore[assignment]
    proposal.sections = sections
    proposal.content = assemble(sections)
    proposal.tone = options["tone"]
    proposal.length = options["length"]
    proposal.warnings = warnings
    proposal.is_simulated = proposal.is_simulated or result.is_simulated
    _record_version(db, proposal, source=source, result=result, cost=cost, used=used, warnings=warnings)
    db.commit()
    db.refresh(proposal)
    return proposal


def snapshot_version(db: Session, proposal: Proposal) -> ProposalVersion:
    v = _record_version(db, proposal, source="manual", result=None, cost=None, used=[], warnings=[])
    db.commit()
    db.refresh(v)
    return v


__all__ = ["SECTIONS", "AppError", "assemble", "generate_proposal", "regenerate_proposal", "snapshot_version"]

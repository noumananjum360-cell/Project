"""Job analysis orchestration: retrieval -> deterministic score -> AI narrative -> persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.base import AIProvider
from app.ai.schemas import AnalysisNarrative
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import Job, JobAnalysis, PortfolioProject, SkillMatch, User, UserPreferences, UserProfile
from app.services.ai_runner import ai_complete
from app.services.notifications import notify
from app.services.portfolio_index import match_portfolio
from app.services.scoring import SCORING_VERSION, compute_fit
from app.services.system_settings import get_setting

log = get_logger(__name__)


def profile_dict(p: UserProfile | None) -> dict[str, Any]:
    if p is None:
        return {}
    return {
        "full_name": p.full_name,
        "headline": p.headline,
        "overview": p.overview,
        "primary_skills": p.primary_skills,
        "additional_skills": p.additional_skills,
        "years_experience": p.years_experience,
        "hourly_rate": str(p.hourly_rate) if p.hourly_rate is not None else None,
        "min_budget": str(p.min_budget) if p.min_budget is not None else None,
        "currency": p.currency,
        "languages": p.languages,
    }


def job_dict(j: Job) -> dict[str, Any]:
    return {
        "title": j.title,
        "description": j.description,
        "budget_min": str(j.budget_min) if j.budget_min is not None else None,
        "budget_max": str(j.budget_max) if j.budget_max is not None else None,
        "currency": j.currency,
        "job_type": j.job_type,
        "required_skills": j.required_skills,
        "experience_level": j.experience_level,
        "client_info": j.client_info,
    }


def _fallback_narrative(det: dict[str, Any]) -> AnalysisNarrative:
    parts = [f"Fit Score {det['fit_score']}/100 ({det['recommendation']})."]
    for b in det["score_breakdown"]:
        parts.append(f"{b['label']}: {b['detail']}")
    return AnalysisNarrative(
        explanation=" ".join(parts)[:3000],
        feasibility_assessment="An AI feasibility review was not available for this analysis.",
        suggested_next_steps=["Review the score breakdown and missing information before applying."],
    )


def analyze_job(db: Session, provider: AIProvider, user: User, job: Job) -> JobAnalysis:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    prof = profile_dict(profile)
    has_projects = bool(db.scalar(select(PortfolioProject.id).where(PortfolioProject.user_id == user.id).limit(1)))
    matches = match_portfolio(db, provider, user.id, job, top_k=3)
    weights = get_setting(db, "scoring_weights")
    thresholds = get_setting(db, "scoring_thresholds")
    det = compute_fit(job_dict(job), prof, matches, has_projects, weights, thresholds)

    narrative_source = "ai"
    model: str | None = provider.chat_model
    try:
        result, _cost = ai_complete(
            db,
            provider,
            user_id=user.id,
            operation="job_analysis",
            system=prompts.ANALYSIS_SYSTEM,
            user=prompts.analysis_user(
                {
                    "job_posting": job_dict(job),
                    "freelancer_profile": prof,
                    "portfolio_projects": [
                        {"id": m["project_id"], "title": m["title"], "evidence": m["evidence"]} for m in matches
                    ],
                    "deterministic_result": {k: v for k, v in det.items() if k != "relevant_portfolio_projects"},
                }
            ),
            schema=AnalysisNarrative,
            temperature=0.2,
        )
        narrative = result.data
        model = result.model
    except AppError as exc:
        log.warning("analysis_narrative_unavailable", code=exc.code)
        narrative = _fallback_narrative(det)
        narrative_source = "deterministic_fallback"

    red_flags = det["red_flags"] + [
        {**f.model_dump(), "category": "risk", "source": "ai"} for f in narrative.additional_red_flags
    ]
    output = {
        **det,
        "red_flags": red_flags,
        "relevant_experience": narrative.relevant_experience,
        "feasibility_assessment": narrative.feasibility_assessment,
        "positive_signals": det["positive_signals"] + [s for s in narrative.positive_signals if s not in det["positive_signals"]],
        "explanation": narrative.explanation,
        "suggested_next_steps": narrative.suggested_next_steps,
        "narrative_source": narrative_source,
        "ai_generated_fields": ["explanation", "feasibility_assessment", "relevant_experience", "suggested_next_steps"]
        if narrative_source == "ai"
        else [],
        "is_simulated": provider.is_simulated,
    }

    analysis = JobAnalysis(
        user_id=user.id,
        job_id=job.id,
        fit_score=det["fit_score"],
        score_confidence=det["score_confidence"],
        recommendation=det["recommendation"],
        result=output,
        weights=weights,
        scoring_version=SCORING_VERSION,
        provider=provider.name,
        model=model,
        embedding_model=provider.embedding_model,
        profile_version=profile.profile_version if profile else None,
        is_simulated=provider.is_simulated,
    )
    db.add(analysis)
    db.flush()
    for s in det["matched_skills"]:
        db.add(SkillMatch(analysis_id=analysis.id, user_id=user.id, skill=s[:100], match_type="matched"))
    for p in det["partially_matched_skills"]:
        db.add(
            SkillMatch(
                analysis_id=analysis.id,
                user_id=user.id,
                skill=p["skill"][:100],
                match_type="partial",
                matched_with=p["via"][:100],
            )
        )
    for s in det["missing_skills"]:
        db.add(SkillMatch(analysis_id=analysis.id, user_id=user.id, skill=s[:100], match_type="missing"))
    job.latest_fit_score = det["fit_score"]
    job.latest_recommendation = det["recommendation"]
    job.analyzed_at = datetime.now(UTC)

    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    threshold = prefs.fit_score_threshold if prefs else 70
    if (prefs is None or prefs.notify_high_fit_jobs) and det["fit_score"] >= threshold:
        notify(
            db,
            user.id,
            "high_fit_job",
            f"High-fit job: {job.title[:150]}",
            f"Fit Score {det['fit_score']} meets your threshold of {threshold}.",
            link=f"/jobs/{job.id}",
            dedupe_key=f"high_fit:{job.id}",
        )
    db.commit()
    db.refresh(analysis)
    return analysis

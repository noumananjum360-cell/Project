"""Dashboard metrics computed from persisted records, scoped to the current user."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import Date, case, cast, func, select

from app.ai.factory import ai_status
from app.api.deps import CurrentUser, DbSession
from app.models import (
    AIUsageLog,
    ApplicationStatusHistory,
    ApplicationTracking,
    Job,
    JobAnalysis,
    Proposal,
    SkillMatch,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _count(db: DbSession, stmt) -> int:  # type: ignore[no-untyped-def]
    return int(db.scalar(stmt) or 0)


@router.get("/summary")
def summary(user: CurrentUser, db: DbSession) -> dict:
    uid = user.id
    statuses = dict(
        db.execute(
            select(ApplicationTracking.status, func.count())
            .where(ApplicationTracking.user_id == uid)
            .group_by(ApplicationTracking.status)
        ).all()
    )
    reached_sent = sum(statuses.get(s, 0) for s in ("sent", "interview", "hired", "declined"))
    ai = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.sum(AIUsageLog.estimated_cost),
            func.count(AIUsageLog.estimated_cost),
        ).where(AIUsageLog.user_id == uid, AIUsageLog.success.is_(True))
    ).one()
    avg = db.scalar(select(func.avg(Job.latest_fit_score)).where(Job.user_id == uid, Job.latest_fit_score.is_not(None)))
    return {
        "total_jobs": _count(db, select(func.count()).select_from(Job).where(Job.user_id == uid)),
        "jobs_analyzed": _count(
            db, select(func.count()).select_from(Job).where(Job.user_id == uid, Job.analyzed_at.is_not(None))
        ),
        "strong_matches": _count(
            db, select(func.count()).select_from(Job).where(Job.user_id == uid, Job.latest_recommendation == "Strong Match")
        ),
        "proposals_generated": _count(db, select(func.count()).select_from(Proposal).where(Proposal.user_id == uid)),
        "proposals_sent": reached_sent,
        "interviews": statuses.get("interview", 0) + statuses.get("hired", 0),
        "hires": statuses.get("hired", 0),
        "average_fit_score": round(float(avg), 1) if avg is not None else None,
        "ai_requests": int(ai[0] or 0),
        "ai_input_tokens": int(ai[1] or 0),
        "ai_output_tokens": int(ai[2] or 0),
        "ai_estimated_cost": float(ai[3]) if ai[4] and ai[3] is not None else None,
        "ai_cost_complete": ai[0] == ai[4],
        "ai_status": ai_status(db),
        "notes": "Sent, interview and hire counts reflect statuses you entered in the tracker.",
    }


@router.get("/analytics")
def analytics(user: CurrentUser, db: DbSession, days: int = Query(default=30, ge=7, le=365)) -> dict:
    uid = user.id
    since = datetime.now(UTC) - timedelta(days=days)

    def per_day(model, col):  # type: ignore[no-untyped-def]
        rows = db.execute(
            select(cast(col, Date).label("d"), func.count()).where(model.user_id == uid, col >= since).group_by("d").order_by("d")
        ).all()
        return {r[0].isoformat(): r[1] for r in rows}

    analyses = per_day(JobAnalysis, JobAnalysis.created_at)
    imports = per_day(Job, Job.created_at)
    proposals = per_day(Proposal, Proposal.created_at)
    all_days = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    timeline = [
        {"date": d, "jobs_imported": imports.get(d, 0), "jobs_analyzed": analyses.get(d, 0), "proposals": proposals.get(d, 0)}
        for d in all_days
    ]

    bucket = case(
        (Job.latest_fit_score < 20, "0-19"),
        (Job.latest_fit_score < 40, "20-39"),
        (Job.latest_fit_score < 60, "40-59"),
        (Job.latest_fit_score < 80, "60-79"),
        else_="80-100",
    )
    dist_rows: dict[Any, int] = dict(
        db.execute(
            select(bucket, func.count()).where(Job.user_id == uid, Job.latest_fit_score.is_not(None)).group_by(bucket)
        ).all()
    )
    distribution = [{"range": r, "count": dist_rows.get(r, 0)} for r in ("0-19", "20-39", "40-59", "60-79", "80-100")]

    status_rows = dict(
        db.execute(
            select(ApplicationTracking.status, func.count())
            .where(ApplicationTracking.user_id == uid)
            .group_by(ApplicationTracking.status)
        ).all()
    )
    order = ["draft", "ready", "sent", "interview", "hired", "declined", "archived"]
    status_breakdown = [{"status": s, "count": status_rows.get(s, 0)} for s in order]
    outcomes = [{"outcome": s, "count": status_rows.get(s, 0)} for s in ("interview", "hired", "declined")]

    # Skills: count each skill once per job (latest analysis per job only).
    latest = (
        select(JobAnalysis.id)
        .where(JobAnalysis.user_id == uid)
        .distinct(JobAnalysis.job_id)
        .order_by(JobAnalysis.job_id, JobAnalysis.created_at.desc())
    ).subquery()
    skill_rows = db.execute(
        select(SkillMatch.skill, func.count())
        .where(SkillMatch.user_id == uid, SkillMatch.match_type == "matched", SkillMatch.analysis_id.in_(select(latest.c.id)))
        .group_by(SkillMatch.skill)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    missing_rows = db.execute(
        select(SkillMatch.skill, func.count())
        .where(SkillMatch.user_id == uid, SkillMatch.match_type == "missing", SkillMatch.analysis_id.in_(select(latest.c.id)))
        .group_by(SkillMatch.skill)
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    return {
        "days": days,
        "timeline": timeline,
        "fit_score_distribution": distribution,
        "status_breakdown": status_breakdown,
        "outcomes": outcomes,
        "top_matched_skills": [{"skill": s, "count": c} for s, c in skill_rows],
        "top_missing_skills": [{"skill": s, "count": c} for s, c in missing_rows],
    }


@router.get("/activity")
def activity(user: CurrentUser, db: DbSession, limit: int = Query(default=15, ge=1, le=50)) -> list[dict]:
    uid = user.id
    events: list[dict] = []
    for j in db.scalars(select(Job).where(Job.user_id == uid).order_by(Job.created_at.desc()).limit(limit)):
        events.append(
            {"type": "job_imported", "at": j.created_at, "title": j.title, "link": f"/jobs/{j.id}", "is_demo": j.is_demo}
        )
    for a, title in db.execute(
        select(JobAnalysis, Job.title)
        .join(Job, Job.id == JobAnalysis.job_id)
        .where(JobAnalysis.user_id == uid)
        .order_by(JobAnalysis.created_at.desc())
        .limit(limit)
    ).all():
        events.append(
            {
                "type": "job_analyzed",
                "at": a.created_at,
                "title": f"{title} — {a.fit_score}/100",
                "link": f"/jobs/{a.job_id}",
                "is_demo": a.is_simulated,
            }
        )
    for p in db.scalars(select(Proposal).where(Proposal.user_id == uid).order_by(Proposal.created_at.desc()).limit(limit)):
        events.append(
            {
                "type": "proposal_generated",
                "at": p.created_at,
                "title": p.title,
                "link": f"/proposals/{p.id}",
                "is_demo": p.is_demo,
            }
        )
    for h, title in db.execute(
        select(ApplicationStatusHistory, Job.title)
        .join(ApplicationTracking, ApplicationTracking.id == ApplicationStatusHistory.application_id)
        .join(Job, Job.id == ApplicationTracking.job_id)
        .where(ApplicationStatusHistory.user_id == uid)
        .order_by(ApplicationStatusHistory.created_at.desc())
        .limit(limit)
    ).all():
        events.append(
            {
                "type": "status_changed",
                "at": h.created_at,
                "title": f"{title}: {h.from_status or 'new'} → {h.to_status}",
                "link": "/tracker",
                "is_demo": False,
            }
        )
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]

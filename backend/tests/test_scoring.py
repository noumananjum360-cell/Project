"""Unit tests for the deterministic Fit Score engine."""

from __future__ import annotations

from app.services.scoring import compute_fit, score_budget, score_risk
from app.services.skills import extract_skills_from_text, match_skills
from app.services.system_settings import DEFAULTS

W = DEFAULTS["scoring_weights"]
T = DEFAULTS["scoring_thresholds"]

PROFILE = {
    "primary_skills": ["React", "TypeScript", "Python"],
    "additional_skills": ["PostgreSQL"],
    "years_experience": 6,
    "hourly_rate": "60",
    "min_budget": "1000",
    "currency": "USD",
}

JOB = {
    "title": "React developer",
    "description": "Build a React dashboard with TypeScript. Requirements: charts, filters, auth. "
    "Deliverables and milestones agreed up front. " * 4,
    "required_skills": ["React", "TypeScript", "Next.js", "GraphQL"],
    "experience_level": "expert",
    "job_type": "hourly",
    "budget_min": "50",
    "budget_max": "80",
    "currency": "USD",
}

MATCHES = [{"project_id": "p1", "title": "Dash", "similarity": 0.62}]


def test_skill_matching_full_partial_missing() -> None:
    m = match_skills(["ReactJS", "Next.js", "GraphQL"], ["React"], ["Docker"])
    assert m["matched"] == ["react"]
    assert m["partial"] == [{"skill": "next.js", "via": "react"}]
    assert m["missing"] == ["graphql"]


def test_extract_skills_from_text() -> None:
    skills = extract_skills_from_text("Looking for a Node.js and PostgreSQL dev with AWS and Docker experience")
    assert {"node.js", "postgresql", "aws", "docker"} <= set(skills)


def test_score_is_normalised_and_explained() -> None:
    r = compute_fit(JOB, PROFILE, MATCHES, True, W, T)
    assert 0 <= r["fit_score"] <= 100
    assert r["score_confidence"] == 1.0
    assert {b["factor"] for b in r["score_breakdown"]} == set(W)
    assert abs(sum(b["effective_weight"] for b in r["score_breakdown"]) - 100) < 0.01
    assert abs(sum(b["points"] for b in r["score_breakdown"]) - r["fit_score"]) <= 1
    assert r["matched_skills"] == ["react", "typescript"]
    assert r["missing_skills"] == ["graphql"]
    assert r["recommendation"] in {"Strong Match", "Possible Match"}


def test_missing_information_is_unknown_and_redistributed() -> None:
    job = {**JOB, "budget_min": None, "budget_max": None, "job_type": "unknown", "experience_level": "unknown"}
    r = compute_fit(job, PROFILE, MATCHES, True, W, T)
    unknown = {b["factor"] for b in r["score_breakdown"] if b["status"] == "unknown"}
    assert unknown == {"budget", "experience"}
    assert r["score_confidence"] == 0.7
    known_eff = sum(b["effective_weight"] for b in r["score_breakdown"] if b["status"] == "known")
    assert abs(known_eff - 100) < 0.01
    # Unknown factors are not treated as zero.
    full = compute_fit(JOB, PROFILE, MATCHES, True, W, T)
    assert r["fit_score"] >= full["fit_score"] - 15
    assert len(r["missing_information"]) == 2


def test_insufficient_information() -> None:
    job = {
        "title": "Help needed",
        "description": "Need help with a thing for my business soon please.",
        "required_skills": [],
        "experience_level": "unknown",
        "job_type": "unknown",
    }
    r = compute_fit(job, {}, [], False, W, T)
    assert r["recommendation"] == "Insufficient Information"
    assert r["score_confidence"] < 0.5


def test_budget_compatibility() -> None:
    f, compat, flags = score_budget({**JOB, "budget_max": "30"}, PROFILE)
    assert compat["status"] == "well_below_preference"
    assert f.score == 0.1
    assert flags and flags[0].category == "budget"
    f, compat, _ = score_budget({**JOB, "currency": "EUR"}, PROFILE)
    assert f.score is None and compat["status"] == "unknown"


def test_red_flags_use_cautious_language() -> None:
    job = {"title": "Easy task", "description": "Contact me on Telegram. First do a free test task, then we pay outside Upwork."}
    f, flags = score_risk(job)
    assert f.score is not None and f.score < 0.5
    assert all(fl.flag.startswith("Potential warning sign") for fl in flags)
    assert not any("fraud" in fl.flag.lower() for fl in flags)


def test_high_severity_flag_blocks_strong_match() -> None:
    job = {**JOB, "description": JOB["description"] + " Please send your bank account details on WhatsApp."}
    r = compute_fit(job, PROFILE, [{"project_id": "p", "title": "x", "similarity": 0.9}], True, W, T)
    assert r["recommendation"] != "Strong Match"


def test_custom_weights() -> None:
    weights = {"skills": 100, "portfolio": 0, "experience": 0, "budget": 0, "scope": 0, "risk": 0}
    r = compute_fit(JOB, PROFILE, MATCHES, True, weights, T)
    # 2 matched + 1 partial (next.js via react) of 4 => 62.5%
    assert r["fit_score"] == 62

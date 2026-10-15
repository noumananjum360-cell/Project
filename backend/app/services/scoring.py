"""Transparent, deterministic Fit Score engine (pure functions, no I/O).

See docs/AI_PIPELINE.md for the full specification. Summary:

* Six factors, each scored in [0, 1] or ``None`` (unknown).
* score = 100 * sum(w_i * s_i for known i) / sum(w_i for known i)
  -> weights of unknown factors are redistributed proportionally.
* confidence = sum(w_i for known i) / sum(all w_i)
* Each signal is counted in exactly one factor (e.g. budget mismatch only
  affects the budget factor, broad scope only the scope factor).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.skills import extract_skills_from_text, match_skills, normalize_skills

SCORING_VERSION = "1.0.0"

FACTOR_LABELS = {
    "skills": "Required-skill match",
    "portfolio": "Relevant portfolio evidence",
    "experience": "Experience & complexity match",
    "budget": "Budget & rate compatibility",
    "scope": "Scope clarity & feasibility",
    "risk": "Client & posting risk",
}

LEVEL_RANK = {"entry": 0, "intermediate": 1, "expert": 2}


@dataclass
class FactorResult:
    score: float | None
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RedFlag:
    flag: str
    evidence: str
    severity: str  # low | medium | high
    category: str  # risk | scope | budget
    source: str = "rules"

    def as_dict(self) -> dict[str, str]:
        return {
            "flag": self.flag,
            "evidence": self.evidence,
            "severity": self.severity,
            "category": self.category,
            "source": self.source,
        }


# --- Red-flag rules: (regex, flag text, severity) -----------------------------
RISK_RULES: list[tuple[str, str, str]] = [
    (
        r"\b(telegram|whats\s?app|signal app|wechat|skype me)\b",
        "Potential warning sign: asks to move communication off-platform",
        "high",
    ),
    (
        r"\b(pay(ment)? (you )?outside|off[- ]platform|outside (of )?(upwork|the platform)|paypal me|direct payment)\b",
        "Potential warning sign: suggests payment outside the platform",
        "high",
    ),
    (
        r"\b(bank account|routing number|social security|ssn\b|passport (scan|copy|number)|credit card (details|number)|"
        r"your (login|password|credentials)|id card (scan|copy))",
        "Potential warning sign: requests sensitive personal or financial information",
        "high",
    ),
    (
        r"\b(registration fee|pay (a|the) fee|purchase (our|a) (kit|starter|software)|send (us )?money|gift cards?|"
        r"upfront (fee|deposit) from you)\b",
        "Potential warning sign: asks the freelancer to pay money",
        "high",
    ),
    (
        r"\b(free (test|trial|sample)|unpaid (test|trial|task|sample)|test task.{0,20}(not|un)paid|"
        r"(work|sample) for free|without pay(ment)?)\b",
        "Potential warning sign: requests unpaid speculative work",
        "medium",
    ),
    (
        r"\b(easy money|earn \$?\d+ (per|a) (day|hour) guaranteed|get rich|no experience needed.{0,30}high pay)\b",
        "Potential warning sign: unusually promotional wording",
        "medium",
    ),
]

DEADLINE_RULES: list[tuple[str, str]] = [
    (r"\b(within|in) (24|12|48) hours\b", "Very short deadline stated"),
    (r"\b(by|before) tomorrow\b", "Very short deadline stated"),
    (r"\b(today|tonight) (urgently|asap)\b", "Very short deadline stated"),
]

DELIVERABLE_CUES = re.compile(
    r"\b(deliverables?|requirements?|must|should|milestones?|timeline|deadline|scope|acceptance|features?|"
    r"responsibilit(y|ies)|tasks?)\b",
    re.I,
)


def _decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except ArithmeticError:
        return None


def years_to_level(years: int | None) -> str | None:
    if years is None:
        return None
    if years < 2:
        return "entry"
    if years < 5:
        return "intermediate"
    return "expert"


# --- Factors ------------------------------------------------------------------
def score_skills(job: dict[str, Any], profile: dict[str, Any]) -> FactorResult:
    required = normalize_skills(job.get("required_skills") or [])
    inferred = False
    if not required:
        required = extract_skills_from_text(f"{job.get('title', '')}\n{job.get('description', '')}", limit=12)
        inferred = True
    have_any = (profile.get("primary_skills") or []) + (profile.get("additional_skills") or [])
    m = match_skills(required, profile.get("primary_skills") or [], profile.get("additional_skills") or [])
    data = {**m, "required": required, "required_inferred": inferred}
    if not required:
        return FactorResult(None, "The job does not list identifiable required skills.", data)
    if not have_any:
        return FactorResult(None, "Your profile has no skills yet, so skills could not be compared.", data)
    s = (len(m["matched"]) + 0.5 * len(m["partial"])) / len(required)
    src = "inferred from the description" if inferred else "listed by the client"
    return FactorResult(
        round(min(1.0, s), 4),
        f"{len(m['matched'])} matched, {len(m['partial'])} partially matched and {len(m['missing'])} missing "
        f"of {len(required)} required skills ({src}).",
        data,
    )


def score_portfolio(matches: list[dict[str, Any]], has_projects: bool, thresholds: dict[str, Any]) -> FactorResult:
    if not has_projects:
        return FactorResult(None, "No portfolio projects to compare yet.", {})
    if not matches:
        return FactorResult(0.0, "No portfolio projects were similar to this job.", {})
    lo = float(thresholds.get("similarity_floor", 0.15))
    hi = float(thresholds.get("similarity_ceiling", 0.6))

    def f(sim: float) -> float:
        return max(0.0, min(1.0, (sim - lo) / (hi - lo))) if hi > lo else 0.0

    sims = [float(m["similarity"]) for m in matches]
    s = 0.7 * f(sims[0]) + 0.3 * f(sum(sims) / len(sims))
    return FactorResult(
        round(s, 4),
        f"Best portfolio similarity {sims[0]:.2f} (“{matches[0]['title']}”) across {len(sims)} retrieved project(s).",
        {"top_similarity": sims[0]},
    )


def score_experience(job: dict[str, Any], profile: dict[str, Any]) -> FactorResult:
    job_level = job.get("experience_level") or "unknown"
    user_level = years_to_level(profile.get("years_experience"))
    if job_level not in LEVEL_RANK:
        return FactorResult(None, "The job does not state an experience level.", {"user_level": user_level})
    if user_level is None:
        return FactorResult(None, "Add your years of experience to compare against the job level.", {"job_level": job_level})
    gap = LEVEL_RANK[user_level] - LEVEL_RANK[job_level]
    s = {0: 1.0, 1: 0.9, 2: 0.8, -1: 0.5, -2: 0.1}[gap]
    detail = {
        True: f"Your experience ({user_level}) meets the requested {job_level} level.",
        False: f"The job requests {job_level} level; your profile suggests {user_level}.",
    }[gap >= 0]
    return FactorResult(s, detail, {"job_level": job_level, "user_level": user_level})


def _ratio_score(ratio: Decimal) -> tuple[float, str]:
    if ratio >= 1:
        return 1.0, "compatible"
    if ratio >= Decimal("0.8"):
        return 0.7, "borderline"
    if ratio >= Decimal("0.6"):
        return 0.4, "below_preference"
    return 0.1, "well_below_preference"


def score_budget(job: dict[str, Any], profile: dict[str, Any]) -> tuple[FactorResult, dict[str, Any], list[RedFlag]]:
    flags: list[RedFlag] = []
    jtype = job.get("job_type") or "unknown"
    top = _decimal(job.get("budget_max")) or _decimal(job.get("budget_min"))
    job_cur = (job.get("currency") or "USD").upper()
    prof_cur = (profile.get("currency") or "USD").upper()
    unknown = {"status": "unknown", "detail": ""}
    if top is None or jtype == "unknown":
        unknown["detail"] = "The client budget or job type is not available."
        return FactorResult(None, unknown["detail"]), unknown, flags
    if job_cur != prof_cur:
        unknown["detail"] = f"Budget is in {job_cur} but your rate is in {prof_cur}; not compared."
        return FactorResult(None, unknown["detail"]), unknown, flags
    pref = _decimal(profile.get("hourly_rate")) if jtype == "hourly" else _decimal(profile.get("min_budget"))
    if pref is None or pref <= 0:
        label = "hourly rate" if jtype == "hourly" else "minimum acceptable budget"
        unknown["detail"] = f"Add your {label} to compare against the client's budget."
        return FactorResult(None, unknown["detail"]), unknown, flags
    s, status = _ratio_score(top / pref)
    unit = "/hr" if jtype == "hourly" else ""
    detail = (
        f"Client budget up to {job_cur} {top}{unit} vs your {'rate' if jtype == 'hourly' else 'minimum'} {prof_cur} {pref}{unit}."
    )
    if status in {"below_preference", "well_below_preference"}:
        flags.append(RedFlag("Budget is below your stated preference", detail, "medium" if s >= 0.4 else "high", "budget"))
    return FactorResult(s, detail), {"status": status, "detail": detail}, flags


def score_scope(job: dict[str, Any], required_count: int) -> tuple[FactorResult, list[RedFlag]]:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    words = len(text.split())
    flags: list[RedFlag] = []
    if words < 40:
        s = 0.3
    elif words < 100:
        s = 0.6
    else:
        s = 0.8
    cues = len(set(m.group(0).lower() for m in DELIVERABLE_CUES.finditer(text)))
    bullets = len(re.findall(r"^\s*([-*•]|\d+[.)])\s+", job.get("description", ""), re.M))
    if cues >= 2 or bullets >= 3:
        s += 0.2
    if words < 40:
        flags.append(
            RedFlag("Potential warning sign: unclear deliverables", f"The description is only {words} words.", "low", "scope")
        )
    if required_count > 12:
        s -= 0.3
        flags.append(
            RedFlag(
                "Potential warning sign: unusually broad scope",
                f"The job asks for {required_count} distinct skills.",
                "medium",
                "scope",
            )
        )
    for pattern, label in DEADLINE_RULES:
        m = re.search(pattern, text, re.I)
        if m:
            s -= 0.2
            flags.append(RedFlag(f"Potential warning sign: {label.lower()}", f"“…{m.group(0)}…”", "low", "scope"))
            break
    s = max(0.0, min(1.0, s))
    return FactorResult(round(s, 4), f"{words} words, {cues} deliverable cue(s), {bullets} list item(s)."), flags


def score_risk(job: dict[str, Any]) -> tuple[FactorResult, list[RedFlag]]:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags: list[RedFlag] = []
    penalty = {"high": 0.5, "medium": 0.25, "low": 0.1}
    s = 1.0
    for pattern, label, severity in RISK_RULES:
        m = re.search(pattern, text, re.I)
        if m:
            s -= penalty[severity]
            start = max(0, m.start() - 40)
            flags.append(RedFlag(label, f"“…{text[start : m.end() + 40].strip()}…”", severity, "risk"))
    client = job.get("client_info") or {}
    if client.get("payment_verified") is False:
        s -= 0.1
        flags.append(
            RedFlag(
                "Potential warning sign: payment method not verified",
                "Client information indicates an unverified payment method.",
                "low",
                "risk",
            )
        )
    rating = client.get("rating")
    if isinstance(rating, (int, float)) and rating < 4.0 and (client.get("reviews_count") or 0) >= 3:
        s -= 0.1
        flags.append(RedFlag("Potential warning sign: low client rating", f"Client rating {rating}/5.", "low", "risk"))
    s = max(0.0, s)
    detail = "No risk indicators detected in the posting." if not flags else f"{len(flags)} potential warning sign(s) found."
    return FactorResult(round(s, 4), detail), flags


# --- Aggregation ---------------------------------------------------------------
def compute_fit(
    job: dict[str, Any],
    profile: dict[str, Any],
    portfolio_matches: list[dict[str, Any]],
    has_projects: bool,
    weights: dict[str, float],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    skills = score_skills(job, profile)
    portfolio = score_portfolio(portfolio_matches, has_projects, thresholds)
    experience = score_experience(job, profile)
    budget, budget_compat, budget_flags = score_budget(job, profile)
    scope, scope_flags = score_scope(job, len(skills.data.get("required", [])))
    risk, risk_flags = score_risk(job)

    factors = {
        "skills": skills,
        "portfolio": portfolio,
        "experience": experience,
        "budget": budget,
        "scope": scope,
        "risk": risk,
    }
    total_w = sum(float(weights.get(k, 0)) for k in factors) or 1.0
    known_w = sum(float(weights.get(k, 0)) for k, f in factors.items() if f.score is not None)
    weighted = sum(float(weights.get(k, 0)) * f.score for k, f in factors.items() if f.score is not None)
    fit = round(100 * weighted / known_w) if known_w > 0 else 0
    confidence = round(known_w / total_w, 3)

    breakdown = []
    for k, f in factors.items():
        w = float(weights.get(k, 0))
        eff = (100 * w / known_w) if (f.score is not None and known_w > 0) else 0.0
        breakdown.append(
            {
                "factor": k,
                "label": FACTOR_LABELS[k],
                "weight": w,
                "effective_weight": round(eff, 2),
                "score": f.score,
                "points": round(eff * f.score, 2) if f.score is not None else None,
                "status": "known" if f.score is not None else "unknown",
                "detail": f.detail,
            }
        )

    flags = risk_flags + scope_flags + budget_flags
    high_flag = any(f.severity == "high" for f in flags)
    min_conf = float(thresholds.get("min_confidence", 0.5))
    if confidence < min_conf:
        rec = "Insufficient Information"
    elif fit >= int(thresholds.get("strong", 75)) and not high_flag:
        rec = "Strong Match"
    elif fit >= int(thresholds.get("possible", 50)):
        rec = "Possible Match"
    else:
        rec = "Weak Match"

    missing_info = [f.detail for f in factors.values() if f.score is None]
    positive = []
    if skills.data.get("matched"):
        positive.append(f"Matches required skills: {', '.join(skills.data['matched'][:5])}")
    if portfolio.score and portfolio.score >= 0.6:
        positive.append("Strong related portfolio evidence")
    if budget_compat["status"] == "compatible":
        positive.append("Budget meets your stated rate or minimum")
    if not risk_flags:
        positive.append("No risk indicators detected in the posting text")

    return {
        "fit_score": int(max(0, min(100, fit))),
        "score_confidence": confidence,
        "recommendation": rec,
        "matched_skills": skills.data.get("matched", []),
        "partially_matched_skills": skills.data.get("partial", []),
        "missing_skills": skills.data.get("missing", []),
        "required_skills_inferred": skills.data.get("required_inferred", False),
        "relevant_portfolio_projects": portfolio_matches,
        "budget_compatibility": budget_compat,
        "red_flags": [f.as_dict() for f in flags],
        "positive_signals": positive,
        "missing_information": missing_info,
        "score_breakdown": breakdown,
        "scoring_version": SCORING_VERSION,
    }

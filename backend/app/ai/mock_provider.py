"""Deterministic, clearly-labelled SIMULATED provider for tests and demo mode.

It never calls a network service. Completions are assembled from the
structured context the services pass in, so outputs are reproducible and
contain only facts present in that context. Embeddings use feature hashing
over normalised tokens, which gives a stable (if simple) semantic signal.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from pydantic import BaseModel

from app.ai.base import CompletionResult, EmbeddingResult, TModel, Usage
from app.ai.schemas import AnalysisNarrative, ProposalDraft, ResumeExtraction, SectionRewrite
from app.services.skills import extract_skills_from_text, normalize_skill

CONTEXT_RE = re.compile(r"<context_json>(.*?)</context_json>", re.S)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.]*")
DIM = 384
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "our",
    "are",
    "will",
    "this",
    "that",
    "from",
    "have",
    "has",
    "need",
    "looking",
    "who",
    "can",
    "a",
    "an",
    "to",
    "of",
    "in",
    "on",
    "is",
    "be",
    "we",
    "i",
    "it",
    "as",
    "or",
    "at",
    "by",
    "us",
    "my",
    "me",
    "all",
    "any",
}


def _context(user_prompt: str) -> dict[str, Any]:
    m = CONTEXT_RE.search(user_prompt)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _tokens(text: str) -> list[str]:
    toks = [t.strip(".") for t in _TOKEN_RE.findall(text.lower())]
    return [normalize_skill(t) for t in toks if t and t not in _STOP and len(t) > 1]


def hashed_embedding(text: str) -> list[float]:
    vec = [0.0] * DIM
    toks = _tokens(text)
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        vec[h % DIM] += 1.0 if (h >> 63) == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider:
    name = "mock"
    chat_model = "bidgenie-simulated-v1"
    embedding_model = "bidgenie-hash-embed-v1"
    is_simulated = True

    def complete_structured(
        self, *, system: str, user: str, schema: type[TModel], operation: str, temperature: float = 0.3
    ) -> CompletionResult[TModel]:
        ctx = _context(user)
        builder = {
            ResumeExtraction: self._resume,
            AnalysisNarrative: self._analysis,
            ProposalDraft: self._proposal,
            SectionRewrite: self._section,
        }.get(schema)
        if builder is None:
            raise ValueError(f"MockProvider has no builder for {schema.__name__}")
        data: BaseModel = builder(ctx)
        return CompletionResult(
            data=schema.model_validate(data.model_dump()),
            model=self.chat_model,
            provider=self.name,
            usage=Usage(_approx_tokens(system + user), _approx_tokens(data.model_dump_json()), 1),
            is_simulated=True,
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[hashed_embedding(t) for t in texts],
            model=self.embedding_model,
            provider=self.name,
            usage=Usage(sum(_approx_tokens(t) for t in texts), 0, 1),
            is_simulated=True,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _resume(ctx: dict[str, Any]) -> ResumeExtraction:
        text: str = ctx.get("resume_text", "")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        years = None
        m = re.search(r"(\d{1,2})\+?\s+years", text, re.I)
        if m:
            years = int(m.group(1))
        langs = [lang for lang in ("English", "Spanish", "French", "German", "Urdu", "Hindi", "Arabic") if lang in text]
        return ResumeExtraction(
            full_name=lines[0][:200] if lines and len(lines[0].split()) <= 5 else None,
            headline=lines[1][:300] if len(lines) > 1 else None,
            overview=" ".join(lines[2:6])[:3000] if len(lines) > 2 else None,
            skills=extract_skills_from_text(text),
            years_experience=years,
            languages=langs,
        )

    @staticmethod
    def _analysis(ctx: dict[str, Any]) -> AnalysisNarrative:
        b = ctx.get("deterministic_result", {})
        matched = b.get("matched_skills", [])
        missing = b.get("missing_skills", [])
        projects = ctx.get("portfolio_projects", [])
        score = b.get("fit_score")
        parts = [f"[Simulated analysis] The deterministic Fit Score is {score}/100."]
        if matched:
            parts.append(f"Your profile lists {len(matched)} of the required skills: {', '.join(matched[:6])}.")
        if missing:
            parts.append(f"Not found on your profile: {', '.join(missing[:6])}.")
        if projects:
            parts.append(f"The closest portfolio evidence is “{projects[0]['title']}”.")
        else:
            parts.append("No closely related portfolio projects were found.")
        steps = []
        if missing:
            steps.append("Decide whether you can honestly cover the missing skills before applying.")
        if projects:
            steps.append(f"Reference “{projects[0]['title']}” as supporting evidence in your proposal.")
        steps.append("Clarify any missing budget or scope details with the client.")
        return AnalysisNarrative(
            explanation=" ".join(parts),
            feasibility_assessment="[Simulated] Feasibility is estimated from description detail and stated requirements only.",
            relevant_experience=[p["title"] for p in projects[:3]],
            positive_signals=[f"Required skill on your profile: {s}" for s in matched[:3]],
            suggested_next_steps=steps,
        )

    @staticmethod
    def _proposal(ctx: dict[str, Any]) -> ProposalDraft:
        job = ctx.get("job", {})
        profile = ctx.get("profile", {})
        projects = ctx.get("portfolio_projects", [])
        matched = ctx.get("matched_skills", []) or profile.get("skills", [])[:3]
        opening = ctx.get("custom_opening")
        title = job.get("title", "your project")
        hook = opening or (
            f"I read your post about “{title}” and the core need is clear to me: "
            f"{(job.get('description') or '').split('.')[0][:180].strip()}."
        )
        skills_txt = ", ".join(matched[:4]) if matched else "the skills listed on my profile"
        solution = (
            f"My approach would be to confirm the exact requirements with you first, then deliver in small, "
            f"reviewable milestones using {skills_txt}. I will share progress regularly so you can give feedback early."
        )
        if projects:
            p = projects[0]
            proof = f"A relevant example from my portfolio is “{p['title']}”: {p['description'][:220].strip()}"
            used = [p["id"]]
        else:
            proof = (
                "I don't have a closely matching portfolio project to point to yet, so I'd be glad to walk you "
                "through my approach in more detail before you decide."
            )
            used = []
        cta = "Would you be open to a short call to confirm scope and timeline?"
        return ProposalDraft(hook=hook, solution=solution, proof=proof, call_to_action=cta, used_project_ids=used)

    @staticmethod
    def _section(ctx: dict[str, Any]) -> SectionRewrite:
        section = ctx.get("section", "hook")
        current = ctx.get("current_text", "")
        return SectionRewrite(text=f"{current.strip()} (Simulated rewrite of the {section}.)".strip())

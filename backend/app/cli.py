"""Management commands.

  python -m app.cli create-admin --email admin@example.com      (prompts for password)
  python -m app.cli seed-demo --email demo@example.com          (prompts for password)

No account is ever created with a default password. Demo seeding is refused
in production and every seeded record is flagged ``is_demo`` and labelled.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from decimal import Decimal

from sqlalchemy import select

from app.ai.factory import get_ai_provider
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import (
    ApplicationStatusHistory,
    ApplicationTracking,
    PortfolioProject,
    Proposal,
    Role,
    User,
    UserProfile,
)
from app.schemas.auth import RegisterIn
from app.schemas.jobs import JobCreate
from app.services import auth_service, job_service
from app.services.analysis_service import analyze_job
from app.services.audit import audit
from app.services.portfolio_index import index_projects
from app.services.proposal_service import generate_proposal

DEMO = "[DEMO] "


def _password(args: argparse.Namespace) -> str:
    pw = os.environ.get("BIDGENIE_BOOTSTRAP_PASSWORD") or (None if args.no_input else getpass.getpass("Password: "))
    if not pw:
        sys.exit("A password is required (prompt, or BIDGENIE_BOOTSTRAP_PASSWORD).")
    try:
        RegisterIn(email=args.email, password=pw)
    except ValueError as exc:
        sys.exit(f"Invalid email or password: {exc}")
    return pw


def create_admin(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == auth_service.normalize_email(args.email)))
        if user is None:
            user = auth_service.register_user(db, args.email, _password(args), args.name)
        user.role = Role.ADMIN
        audit(db, "cli.admin_bootstrap", actor_id=None, target_type="user", target_id=user.id)
        db.commit()
        print(f"Admin ready: {user.email}")
    finally:
        db.close()


DEMO_PROJECTS = [
    {
        "title": "Analytics dashboard for a subscription business (fictional)",
        "description": "Built a React and TypeScript dashboard with a FastAPI backend and PostgreSQL. Included "
        "role-based access, charts with Recharts and CSV exports.",
        "skills": ["React", "TypeScript", "FastAPI", "PostgreSQL"],
        "category": "Web development",
        "role": "Full-stack developer",
    },
    {
        "title": "Document Q&A assistant prototype (fictional)",
        "description": "Prototype retrieval-augmented chatbot that answers questions over PDF manuals using "
        "embeddings, a vector database and the OpenAI API, with a Python backend.",
        "skills": ["Python", "OpenAI", "RAG", "ChromaDB"],
        "category": "AI / ML",
        "role": "AI engineer",
    },
    {
        "title": "Landing page for a local bakery (fictional)",
        "description": "Responsive WordPress landing page with a contact form and online ordering via WooCommerce.",
        "skills": ["WordPress", "WooCommerce", "CSS"],
        "category": "Web design",
        "role": "Web designer",
    },
]

DEMO_JOBS = [
    {
        "title": "React + FastAPI developer for internal analytics tool",
        "description": "We need a developer to build an internal analytics tool. Requirements: React with "
        "TypeScript front end, FastAPI backend, PostgreSQL. Deliverables: dashboards, filters, user roles. "
        "Milestones agreed up front; expected timeline is 6 weeks.",
        "job_type": "hourly",
        "budget_min": Decimal("45"),
        "budget_max": Decimal("75"),
        "required_skills": ["React", "TypeScript", "FastAPI", "PostgreSQL"],
        "experience_level": "expert",
    },
    {
        "title": "Build a RAG chatbot over our support docs",
        "description": "Looking for someone to build a chatbot that answers customer questions from our help "
        "center articles. Should use embeddings and a vector database. Python preferred. Must include "
        "an admin page to re-index content.",
        "job_type": "fixed",
        "budget_max": Decimal("2500"),
        "required_skills": ["Python", "OpenAI", "RAG", "Vector Databases"],
        "experience_level": "intermediate",
    },
    {
        "title": "Quick logo + full brand + website + mobile app",
        "description": "Need logo, brand book, website, iOS and Android app, SEO and ads. Do a free test task "
        "first. Contact me on Telegram for details. Budget is small.",
        "job_type": "fixed",
        "budget_max": Decimal("150"),
        "required_skills": ["Logo Design", "Branding", "Flutter", "SEO", "Google Ads", "WordPress"],
        "experience_level": "entry",
    },
]


def seed_demo(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.is_production:
        sys.exit("Refusing to seed demo data in production.")
    db = SessionLocal()
    try:
        email = auth_service.normalize_email(args.email)
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = auth_service.register_user(db, email, _password(args), "Demo Freelancer")
        user.onboarding_completed = True
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        assert profile is not None
        profile.full_name = "Demo Freelancer"
        profile.headline = f"{DEMO}Full-stack & AI developer (sample profile)"
        profile.overview = "This is a fictional demonstration profile used to evaluate BidGenie AI."
        profile.primary_skills = ["React", "TypeScript", "Python", "FastAPI"]
        profile.additional_skills = ["PostgreSQL", "OpenAI", "RAG", "Docker"]
        profile.years_experience = 6
        profile.hourly_rate = Decimal("55.00")
        profile.min_budget = Decimal("800.00")
        profile.languages = ["English"]
        profile.is_demo = True
        db.commit()

        if not db.scalar(
            select(PortfolioProject.id).where(PortfolioProject.user_id == user.id, PortfolioProject.is_demo.is_(True))
        ):
            for p in DEMO_PROJECTS:
                db.add(PortfolioProject(user_id=user.id, is_demo=True, **p))
            db.commit()

        jobs = []
        for j in DEMO_JOBS:
            data = JobCreate.model_validate({**j, "title": DEMO + str(j["title"])})
            job, _created = job_service.create_job(db, user.id, data, source="demo", is_demo=True)
            jobs.append(job)
        db.commit()

        try:
            provider = get_ai_provider(db)
        except AppError as exc:
            print(f"Seeded profile, portfolio and jobs. Skipped analyses/proposals: {exc.message}")
            return
        projects = list(db.scalars(select(PortfolioProject).where(PortfolioProject.user_id == user.id)))
        index_projects(db, provider, projects)
        for job in jobs:
            analyze_job(db, provider, user, job)
        proposal = db.scalar(select(Proposal).where(Proposal.user_id == user.id, Proposal.job_id == jobs[0].id))
        if proposal is None:
            proposal = generate_proposal(db, provider, user, jobs[0], {"tone": "professional", "length": "standard"})
            proposal.is_demo = True
        if not db.scalar(
            select(ApplicationTracking.id).where(ApplicationTracking.user_id == user.id, ApplicationTracking.job_id == jobs[0].id)
        ):
            app_row = ApplicationTracking(
                user_id=user.id,
                job_id=jobs[0].id,
                proposal_id=proposal.id,
                proposal_version_number=1,
                status="ready",
                is_demo=True,
                notes=f"{DEMO}Sample tracking record.",
            )
            db.add(app_row)
            db.flush()
            db.add(ApplicationStatusHistory(application_id=app_row.id, user_id=user.id, to_status="ready"))
        db.commit()
        label = " (SIMULATED AI)" if provider.is_simulated else ""
        print(f"Demo data ready for {email}{label}.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin", help="Create or promote an administrator")
    a.add_argument("--email", required=True)
    a.add_argument("--name", default=None)
    a.add_argument("--no-input", action="store_true", help="Read password from BIDGENIE_BOOTSTRAP_PASSWORD only")
    a.set_defaults(func=create_admin)
    s = sub.add_parser("seed-demo", help="Create clearly-labelled demonstration data (non-production only)")
    s.add_argument("--email", required=True)
    s.add_argument("--no-input", action="store_true")
    s.set_defaults(func=seed_demo)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

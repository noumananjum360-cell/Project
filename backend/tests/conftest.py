from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["VECTOR_STORE"] = "memory"
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "1000"
os.environ["RATE_LIMIT_AI_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.ai.factory import set_provider_override  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.rate_limit import limiter  # noqa: E402
from app.services.email import OUTBOX  # noqa: E402
from app.vector_store.factory import set_vector_store_override  # noqa: E402
from app.vector_store.stores import InMemoryVectorStore  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = "CorrectHorse9Battery"


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, env=os.environ.copy())


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    limiter.reset()
    OUTBOX.clear()
    set_vector_store_override(InMemoryVectorStore())
    set_provider_override(None)
    yield
    set_provider_override(None)


@pytest.fixture
def db():  # type: ignore[no-untyped-def]
    s = SessionLocal()
    yield s
    s.close()


class Client(TestClient):
    """TestClient that sends the CSRF header captured at login."""

    csrf: str | None = None

    def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def,override]
        if self.csrf and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-CSRF-Token", self.csrf)
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def make_client(email: str = "alice@example.com", password: str = PASSWORD, *, register: bool = True) -> Client:
    c = Client(app)
    if register:
        r = c.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Alice Example"})
        assert r.status_code == 201, r.text
        c.csrf = r.json()["csrf_token"]
    return c


@pytest.fixture
def client() -> Client:
    return make_client()


@pytest.fixture
def other_client() -> Client:
    return make_client("bob@example.com")


def make_admin(email: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role='ADMIN' WHERE email=:e"), {"e": email})


SAMPLE_PROFILE = {
    "full_name": "Alice Example",
    "headline": "Full-stack developer (React, FastAPI)",
    "overview": "I build web applications with React and Python.",
    "primary_skills": ["React", "TypeScript", "Python", "FastAPI"],
    "additional_skills": ["PostgreSQL", "Docker"],
    "years_experience": 6,
    "hourly_rate": "60.00",
    "currency": "USD",
    "min_budget": "1000.00",
    "proposal_tone": "professional",
    "proposal_length": "standard",
    "languages": ["English"],
}

SAMPLE_PROJECT = {
    "title": "Inventory dashboard for a retail team",
    "description": "Built a React and TypeScript dashboard with a FastAPI backend and PostgreSQL database "
    "to track inventory levels and purchase orders.",
    "skills": ["React", "TypeScript", "FastAPI", "PostgreSQL"],
    "category": "Web development",
    "role": "Lead developer",
}

SAMPLE_JOB = {
    "title": "React + FastAPI developer for analytics dashboard",
    "description": "We need an experienced developer to build an analytics dashboard. Requirements: React "
    "front end with TypeScript, FastAPI backend, PostgreSQL. Deliverables include charts, filters and "
    "authentication. Milestones will be agreed up front and the timeline is six weeks.",
    "budget_min": "50",
    "budget_max": "80",
    "job_type": "hourly",
    "required_skills": ["React", "TypeScript", "FastAPI", "PostgreSQL"],
    "experience_level": "expert",
    "url": "https://www.upwork.com/jobs/~01abcdef1234567890?source=rss",
}

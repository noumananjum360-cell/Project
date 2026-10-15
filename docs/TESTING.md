# Testing

All automated tests use the **deterministic mock AI provider**. No live OpenAI calls are made. Run live-provider checks manually with a real key in a non-production environment.

## Backend (pytest)

```bash
createdb bidgenie_test        # owned by your DB user
cd backend && pytest
```

`TEST_DATABASE_URL` overrides the default `postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie_test`. The suite drops and recreates the schema, runs **Alembic migrations** (so migrations are tested), and truncates tables between tests.

| File | Covers |
| --- | --- |
| `test_auth.py` | register/login/me/logout, duplicates, weak passwords, generic invalid-credential errors, protected routes, CSRF, extension bearer flow, refresh rotation + reuse detection, cookie refresh, password reset (single-use), email verification, password change, rate limiting, export, account deletion |
| `test_profile_portfolio.py` | profile CRUD + validation, preferences, DOCX/PDF resume parse → review → apply → delete, invalid/malformed/oversized files, portfolio CRUD, search, embedding dedupe on reindex, URL validation |
| `test_jobs_analysis.py` | job CRUD, URL + fingerprint dedup, validation, all filters and pagination, CSV import (dedup, per-line errors, required columns), paste parsing, full analysis output contract, semantic portfolio ranking, notifications, stale-profile detection, prompt-injection containment, missing AI key (503 + non-AI features keep working), mock refused in production, provider failure logging |
| `test_scoring.py` | skill matching, normalisation to 100, unknown-factor redistribution, insufficient information, budget compatibility, cautious red flags, high-severity cap, custom weights |
| `test_vector_store.py` | Chroma / FAISS / memory ranking, user isolation, deletion, persistence across instances |
| `test_proposals_tracking.py` | generation structure, edit persistence, versions, section + full regeneration, restore, export, honest proposal without portfolio, custom opening, selected projects, unverified-figure detection, tracking + history, follow-up reminders, dashboard/analytics from persisted data, **cross-user isolation**, admin authorization, usage limits, deactivation, audit log |

Lint and types: `ruff check app tests`, `mypy app --ignore-missing-imports`.

## Frontend

```bash
cd frontend
npm test            # Vitest + React Testing Library
npm run lint && npm run typecheck && npm run build
```

Unit tests cover auth form validation, the generic login error, sign-in, protected and admin routes, profile validation and save (incl. CSRF header), job feed loading/error/retry, paste import with review, analysis display (unknown factors, simulated badge, warnings, stale notice), proposal autosave debounce and clipboard copy, tracker status updates, and the mobile navigation drawer.

### End-to-end (Playwright)

```bash
createdb bidgenie_e2e
cd frontend && npx playwright test
```

Playwright starts a demo-mode backend (8001), a backend with **no AI configured** (8002) and two Vite servers. Scenarios:

1. Register → onboarding (profile + portfolio) → import a job → analyze (Fit Score, portfolio retrieval) → generate a proposal → edit → autosave → **reload persists** → mark ready → tracker status → dashboard reflects the changes.
2. A second user cannot open the first user's job.
3. With no AI key, analysis shows a clear "not configured" error.
4. Mobile (Pixel 7): no horizontal overflow on key pages; the navigation drawer works.

## Extension

```bash
cd extension
npm test                       # fixtures, message validation, API client
npm run build && npx playwright test   # real Chromium + real backend on :8000 (uses DB bidgenie_e2e)
```

The browser test loads the unpacked extension, signs in via the popup, clicks the injected button on a fixture served at an upwork.com URL, and verifies the saved job, analysis and proposal through the API. It also checks that malformed messages are rejected.

## Not automated

* Live OpenAI responses (needs a key).
* Live Upwork pages (needs an authorised environment; markup may differ from fixtures).
* SMTP delivery.

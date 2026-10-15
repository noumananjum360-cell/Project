# BidGenie AI

BidGenie AI is an AI-powered assistant for freelancers on Upwork. It helps you decide **whether a job is worth applying for** and drafts an **honest, personalised proposal** from facts you have verified. It ships as a web app (React + FastAPI + PostgreSQL) and a Chrome extension (Manifest V3).

> BidGenie never submits proposals, clicks "Apply" or spends Connects for you. It does not guarantee interviews or hires. Every AI output is editable, and AI output is clearly labelled.

## 1. Features

| Area | What's implemented |
| --- | --- |
| Auth | Register, login, logout, refresh-token rotation with reuse detection, password change/reset, email verification (SMTP), account deletion, data export, USER/ADMIN roles |
| Profile | Full freelancer profile, preferences, PDF/DOCX resume upload → extraction → **review screen** → confirmed apply |
| Portfolio | CRUD, search/filter, automatic embedding on change, index rebuild, per-project index status |
| Jobs | Manual entry, paste-and-review, CSV import, extension import, de-duplication (URL + content fingerprint), rich filters, sorting, pagination, archive |
| Fit Score | Transparent 6-factor deterministic score (0–100), unknown-factor redistribution, confidence, red flags with evidence, AI-written explanation, versioned analyses |
| Vector search | ChromaDB (default) or FAISS behind one interface; strictly user-scoped; DB re-checks ownership |
| Proposals | Hook → Solution → Proof → CTA, tone/length/options, section or full regeneration, fabrication guards, autosave, versions, restore, copy, TXT/MD export |
| Tracker | List + Kanban, 7 statuses, status history, follow-up reminders, contract value |
| Dashboard | KPIs and charts computed from your own records, AI usage/cost |
| Admin | Users (activate/deactivate), usage & AI errors, health, scoring weights, AI model settings, usage limits, audit log |
| Extension | Popup, side panel, injected panel, user-triggered extraction, analysis + proposal, copy, open dashboard |

## 2. Technology stack

* **Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, React Router, TanStack Query, React Hook Form, Zod, Recharts, Lucide
* **Backend:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL (psycopg 3), PyJWT, Argon2id, structlog
* **AI:** OpenAI API (or any OpenAI-compatible endpoint), embeddings, ChromaDB / FAISS, deterministic mock provider for tests and demos
* **Extension:** Manifest V3, TypeScript, React, esbuild
* **Tooling:** Docker Compose, Pytest, Vitest + React Testing Library, Playwright, Ruff, mypy, ESLint

## 3. Architecture overview

```mermaid
flowchart LR
  U[Browser] -->|HTTPS, cookies + CSRF| N[nginx / Vite]
  N -->|/api| B[FastAPI]
  X[Chrome extension] -->|Bearer token| B
  B --> P[(PostgreSQL)]
  B --> V[(ChromaDB / FAISS)]
  B --> AI[OpenAI-compatible API]
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## 4. Prerequisites

* Docker 24+ with Compose v2, **or** Python 3.12, Node 20+ (22 recommended) and PostgreSQL 14+
* An OpenAI API key for real AI features (optional for demo mode)
* Chrome 116+ for the extension

## 5. Repository structure

```
backend/     FastAPI app (app/api, core, db, models, schemas, repositories, services, ai, vector_store, security, tasks), Alembic, tests
frontend/    React app (src/components, layouts, pages, features/*, hooks, lib, services, types, routes), unit + e2e tests
extension/   Chrome MV3 extension (src/background, content, popup, sidepanel, services, shared), tests, browser e2e
infra/       docker-compose.yml
scripts/     helper scripts (e2e backend launcher)
docs/        architecture, API, database, AI pipeline, extension, deployment, security, testing
```

## 6. Environment setup

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, JWT_SECRET_KEY and OPENAI_API_KEY (or enable demo mode, below)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # good JWT_SECRET_KEY
```

**Demo mode (no paid key):** set `AI_PROVIDER=mock` and `DEMO_MODE=true`. Every AI result is labelled **Simulated AI** in the UI and API. Demo mode is refused when `ENVIRONMENT=production`.

## 7. Docker startup

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
open http://localhost:8080            # web app (nginx serves the SPA and proxies /api)
curl http://localhost:8000/health     # backend
```

Migrations run automatically in the one-shot `migrate` service before the backend starts. Postgres data (`pgdata`) and vectors (`backend-data`) persist in named volumes.

If your network uses a TLS-intercepting proxy, set `EXTRA_CA_FILE=/path/to/ca.pem` in `.env`; it is passed to the image builds as a BuildKit secret and never stored in the images.

## 8. Database initialization

The database is created by Postgres (compose) or by you (`createdb bidgenie`). Then:

```bash
# create an administrator (prompts for a password; no default passwords exist)
docker compose -f infra/docker-compose.yml --env-file .env exec backend python -m app.cli create-admin --email you@example.com
# optional, non-production only: clearly-labelled demo data
docker compose -f infra/docker-compose.yml --env-file .env exec backend python -m app.cli seed-demo --email demo@example.com
```

## 9. Migration commands

```bash
cd backend
alembic upgrade head                              # apply
alembic revision --autogenerate -m "describe"     # create after model changes
alembic check                                     # verify models and migrations match
alembic downgrade -1                              # roll back one
```

## 10. AI provider configuration

| Variable | Purpose |
| --- | --- |
| `AI_PROVIDER` | `openai`, `openai_compatible` (with `OPENAI_BASE_URL`) or `mock` (tests/demo only) |
| `OPENAI_API_KEY` | Server-side only. Never sent to the browser or extension |
| `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL` | Model names (admins can override at runtime) |
| `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` | Timeouts and bounded retries |
| `AI_PRICING_JSON` | Per-model USD prices for cost estimates; unknown models show "—" |

Without a key, AI endpoints return `503 ai_not_configured` with a clear message and the UI shows a banner; everything else keeps working. See [docs/AI_PIPELINE.md](docs/AI_PIPELINE.md).

## 11. Vector database configuration

`VECTOR_STORE=chroma` (default, persisted at `CHROMA_PERSIST_DIRECTORY`) or `faiss` (persisted at `FAISS_INDEX_DIRECTORY`). To rebuild a user's index: **Portfolio → Rebuild index**, or `POST /api/v1/portfolio/reindex?force=true`. Changing the embedding model creates a new collection and requires a reindex.

## 12. Running the frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run build      # production build in dist/
```

## 13. Running the backend

```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000     # API docs at http://localhost:8000/docs (non-production)
```

## 14. Running automated tests

```bash
# backend (needs a Postgres test DB; default postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie_test)
cd backend && pytest && ruff check app tests && mypy app --ignore-missing-imports
# frontend unit tests, lint, types
cd frontend && npm test && npm run lint && npm run typecheck
# frontend end-to-end (starts two backends + two Vite servers; needs DB bidgenie_e2e)
cd frontend && npx playwright test
# extension unit tests and browser test against a live backend
cd extension && npm test && npm run build && npx playwright test
```

See [docs/TESTING.md](docs/TESTING.md).

## 15. Building the Chrome extension

```bash
cd extension && npm ci && npm run build      # output: extension/dist
npm run package                              # zip for the Chrome Web Store
```

## 16. Loading the extension in Chrome

1. Open `chrome://extensions` and enable **Developer mode**.
2. Click **Load unpacked** and choose `extension/dist`.
3. Click the BidGenie icon, open **Connection settings**, set the backend URL (default `http://localhost:8000`) and dashboard URL, then sign in.

Details: [docs/CHROME_EXTENSION.md](docs/CHROME_EXTENSION.md).

## 17. Production deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): managed Postgres, persistent volume for vectors, HTTPS, `ENVIRONMENT=production`, `COOKIE_SECURE=true`, migrations before rollout, backups and monitoring hooks.

## 18. Security considerations

Argon2id hashing, short-lived JWT access tokens, rotating hashed refresh tokens with reuse detection, HttpOnly cookies + double-submit CSRF, strict CORS, rate limits, upload validation by magic bytes, user-scoped queries everywhere, audit logging, prompt-injection containment, secret redaction in logs. See [docs/SECURITY.md](docs/SECURITY.md).

## 19. Integration status

| Integration | Status |
| --- | --- |
| PostgreSQL, Alembic, ChromaDB, FAISS | Fully implemented and tested |
| OpenAI / OpenAI-compatible LLM + embeddings | Implemented; **requires `OPENAI_API_KEY`**. Automated tests use the mock provider; no live-provider call was made during development |
| SMTP email (reset/verification) | Implemented; **requires SMTP settings**. Without them, links are logged in development only |
| Chrome extension ↔ backend | Implemented and tested in Chromium against a live backend using **representative HTML fixtures** |
| Live Upwork pages | **Not verified.** Extraction targets visible page content and may need selector updates; requires use consistent with Upwork's terms. Manual paste/CSV import always works |
| Upwork API / automated polling | **Not implemented**: requires Upwork API approval. No unofficial endpoints or scraping are used |

## 20. Known limitations

* Rate limiting and BackgroundTasks are in-process (correct for one backend instance). Use a shared store/worker for horizontal scaling.
* Resume parsing does not OCR scanned (image-only) PDFs.
* Fit Score skill matching uses a curated alias/family table; uncommon skills only match exactly.
* Proposal "unverified figure" checks are heuristic; always review before sending.
* Extension extraction depends on page markup that may change.

## 21. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Banner "AI features are not configured" | Set `OPENAI_API_KEY` (or demo mode) and restart the backend |
| `403 csrf_failed` | Use the app through one origin (Vite proxy or nginx); clear cookies and sign in again |
| Cookies not set in production | `COOKIE_SECURE=true` requires HTTPS; check `COOKIE_DOMAIN` |
| Portfolio shows "Not indexed" | Configure AI, then **Rebuild index** |
| Docker build fails on pip/npm TLS errors | Set `EXTRA_CA_FILE` to your proxy CA bundle |
| Docker Hub `429 Too Many Requests` | `docker login`, or pull the base images from a mirror and re-tag them |
| Extension: "Backend unreachable" | Check the backend URL in the popup; for non-local hosts use HTTPS and grant the permission prompt |
| Backend refuses to start in production | Read the error: it lists unsafe settings (weak `JWT_SECRET_KEY`, `COOKIE_SECURE=false`, demo mode) |

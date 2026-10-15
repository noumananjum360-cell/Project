# Deployment

**Status:** no public deployment has been made. These are the instructions for one.

## Recommended topology

```mermaid
flowchart LR
  User -->|HTTPS| LB[TLS load balancer / reverse proxy]
  LB --> FE[frontend container: nginx + SPA, proxies /api]
  FE --> BE[backend container(s)]
  BE --> PG[(Managed PostgreSQL)]
  BE --> VOL[(Persistent volume: /data/chroma)]
  BE --> AI[OpenAI API]
```

* **Frontend:** the `frontend` image (nginx) on any container host, or `npm run build` on a static host with a same-origin `/api` reverse proxy.
* **Backend:** the `backend` image on a container platform (Fly.io, Render, ECS, Cloud Run with a mounted volume, Kubernetes). Run **one replica** unless you replace the in-process rate limiter and background tasks (see SECURITY.md).
* **Database:** managed PostgreSQL 14+ with automated backups and PITR.
* **Vectors:** a persistent volume mounted at `/data` (ChromaDB). Vectors can always be rebuilt from PostgreSQL with `POST /portfolio/reindex?force=true`.

## Production environment

```
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/bidgenie?sslmode=require
FRONTEND_URL=https://app.example.com
BACKEND_URL=https://app.example.com
JWT_SECRET_KEY=<48+ random chars from a secret manager>
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
AI_PROVIDER=openai
OPENAI_API_KEY=<from secret manager>
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
AI_PRICING_JSON={...}
DEMO_MODE=false
CHROMA_PERSIST_DIRECTORY=/data/chroma
LOG_JSON=true
SMTP_HOST=... SMTP_USERNAME=... SMTP_PASSWORD=...
```

The backend **refuses to start** in production with a default or short JWT secret, `COOKIE_SECURE=false`, demo mode, the mock provider, or a non-HTTPS `FRONTEND_URL`. API docs (`/docs`) are disabled in production.

Inject secrets through the platform's secret manager. They are never baked into images (`.dockerignore` excludes `.env`).

## Build and release

```bash
docker build -t bidgenie-backend:$(git rev-parse --short HEAD) backend
docker build -t bidgenie-frontend:$(git rev-parse --short HEAD) frontend
# 1. run migrations (one-off job) BEFORE rolling out the new backend
docker run --rm --env-file prod.env bidgenie-backend:TAG alembic upgrade head
# 2. roll out backend, then frontend
# 3. bootstrap an admin once
docker run --rm -it --env-file prod.env bidgenie-backend:TAG python -m app.cli create-admin --email you@example.com
```

Migrations are additive-first. For destructive changes, deploy in two steps (expand, then contract).

## HTTPS, domain, CORS

* Terminate TLS at the load balancer and redirect HTTP to HTTPS. The backend adds HSTS in production. uvicorn runs with `--proxy-headers`.
* Serve SPA and API from the **same origin** (recommended), so the default `lax` cookies work and CORS stays closed. If the API is on another origin, add the SPA origin to `CORS_EXTRA_ORIGINS` and set `COOKIE_SAMESITE=none` with `COOKIE_SECURE=true`.
* The extension calls the API from its service worker using host permissions. It needs no CORS entry.

## Health checks and logs

* Liveness `GET /health`; readiness `GET /health/ready` (returns 503 if the DB is down). Frontend: `GET /healthz`.
* Logs are structured JSON on stdout with request ids (`X-Request-ID`) and secret redaction. Ship them to your log platform.

## Monitoring hooks

* Backend: add Sentry/OpenTelemetry in `app/main.py` (the unhandled-exception handler in `core/errors.py` is the single choke point).
* Frontend: `ErrorBoundary.componentDidCatch` in `src/pages/StatusPages.tsx`.
* Admin → Usage / Health shows AI error rates and pending embeddings.

## Backups and recovery

* PostgreSQL: daily snapshots plus PITR, and test restores quarterly.
* Vector volume: optional snapshots. Recovery = restore DB, then reindex.
* Retention: resumes aren't stored unless `RESUME_RETAIN_FILES=true`. Users can export and delete their data.

## Extension release

```bash
cd extension && npm ci && npm run package
```

Upload `bidgenie-extension.zip` to the Chrome Web Store. Document the backend URL users must enter and the permissions in the listing.

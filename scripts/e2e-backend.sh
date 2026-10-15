#!/usr/bin/env bash
# Starts an isolated backend for Playwright end-to-end tests.
#   PORT        port to listen on (default 8001)
#   E2E_AI      "mock" (simulated AI, demo mode) or "none" (no AI configured)
#   E2E_RESET   "1" to reset the e2e database schema and run migrations
set -euo pipefail
cd "$(dirname "$0")/../backend"
PORT="${PORT:-8001}"
export ENVIRONMENT=development
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie_e2e}"
export FRONTEND_URL="${E2E_FRONTEND_URL:-http://localhost:5174}"
export CORS_EXTRA_ORIGINS="http://localhost:5175"
export JWT_SECRET_KEY="e2e-only-secret-key-not-for-production-0123456789"
export VECTOR_STORE=chroma
export CHROMA_PERSIST_DIRECTORY="${TMPDIR:-/tmp}/bidgenie-e2e-chroma-${PORT}"
export LOG_LEVEL=WARNING
export RATE_LIMIT_AUTH_PER_MINUTE=1000
if [[ "${E2E_AI:-mock}" == "mock" ]]; then
  export AI_PROVIDER=mock DEMO_MODE=true
else
  export AI_PROVIDER=openai DEMO_MODE=false
  unset OPENAI_API_KEY || true
fi
PY="${PYTHON:-.venv/bin/python}"
if [[ "${E2E_RESET:-0}" == "1" ]]; then
  rm -rf "$CHROMA_PERSIST_DIRECTORY"
  "$PY" - <<'PYEOF'
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ["DATABASE_URL"])
with e.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
PYEOF
  "$PY" -m alembic upgrade head
fi
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"

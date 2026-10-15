# API reference

Base path: `/api/v1`. Interactive OpenAPI docs: `/docs` (disabled in production).

## Conventions

* **Auth:** browser sessions use HttpOnly cookies (`bg_access`, `bg_refresh`) plus a CSRF cookie `bg_csrf`; send its value in `X-CSRF-Token` on POST/PUT/PATCH/DELETE. The extension uses `Authorization: Bearer <access_token>` (no CSRF needed).
* **Errors:** `{"error": {"code": "...", "message": "...", "details": ...}}`. Common codes: `validation_error` (422), `unauthorized`/`token_expired` (401), `forbidden`/`csrf_failed` (403), `not_found` (404; also returned for other users' records), `conflict`/`duplicate_job` (409), `rate_limited`/`usage_limit_reached` (429), `ai_not_configured`/`ai_timeout`/`ai_rate_limited` (503), `ai_invalid_output` (502).
* **Pagination:** `?page=1&page_size=20` → `{items, total, page, page_size, pages}`.
* **Money:** decimal strings, e.g. `"60.00"`.

## Auth `/auth`

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/register` | `{email, password, full_name?}` → sets cookies, returns `{user, csrf_token}` |
| POST | `/login` | `{email, password, client: "web"\|"extension"}`; extension receives `tokens` |
| POST | `/refresh` | Cookie (web, CSRF) or `{refresh_token}` (extension); rotates token |
| POST | `/logout` | Revokes refresh token, clears cookies |
| GET/PATCH | `/me` | Current user / update name, onboarding flag |
| GET | `/session` | Current user + CSRF token |
| POST | `/change-password` | Revokes other sessions |
| POST | `/forgot-password`, `/reset-password` | Generic response; single-use hashed tokens |
| POST | `/verify-email`, `/resend-verification` | Email verification |

## Account `/account`
`GET /export` (JSON export) · `DELETE ""` `{password}` (deletes account, files, vectors)

## Profile `/profile`
`GET ""` · `PUT ""` · `DELETE ""` (clear fields) · `GET/PUT /preferences` · `POST /resume` (multipart `file`) · `GET /resume` · `POST /resume/apply` (confirmed fields) · `DELETE /resume`

## Portfolio `/portfolio`
`GET ""` (`q`, `skill`, `category`, `sort`) · `POST ""` · `GET/PUT/DELETE /{id}` · `POST /reindex?force=`

## Jobs `/jobs`
| Method | Path | Notes |
| --- | --- | --- |
| GET | `""` | Filters: `q`, `exclude`, `skills`, `budget_min`, `budget_max`, `job_type`, `experience_level`, `posted_after`, `min_score`, `analyzed`, `status`, `source`, `sort` |
| POST | `""?source=manual\|paste` | 409 `duplicate_job` with `existing_job_id` |
| POST | `/from-extension` | Used by the extension |
| POST | `/parse-text` | Extract fields from pasted text (not saved) |
| POST | `/import/csv` | Multipart CSV; returns import summary with per-line errors |
| GET | `/imports` | Import history |
| GET/PUT/PATCH/DELETE | `/{id}` | PATCH = status/notes only |
| POST | `/{id}/analyze` | Runs Fit Score analysis (AI required) |
| GET | `/{id}/analysis`, `/{id}/analyses` | Latest / history |
| POST | `/{id}/match-portfolio?top_k=3` | Semantic matches with evidence |

## Proposals `/proposals`
`GET ""` · `POST /generate` `{job_id, tone?, length?, emphasize_skills?, project_ids?, custom_opening?, exclude?}` · `GET/PUT/DELETE /{id}` · `POST /{id}/regenerate` `{section?, tone?, length?, ...}` · `POST/GET /{id}/versions` · `POST /{id}/versions/{n}/restore` · `GET /{id}/export?format=txt|md`

## Applications `/applications`
`GET ""` (`status`, `q`) · `POST ""` `{job_id, proposal_id?, status?, notes?, follow_up_at?}` · `GET/PUT/DELETE /{id}` (PUT accepts `status`, `status_note`, dates, `contract_value`, `notes`)

## Dashboard, notifications
`GET /dashboard/summary` · `GET /dashboard/analytics?days=30` · `GET /dashboard/activity` · `GET /notifications` · `POST /notifications/{id}/read` · `POST /notifications/read-all`

## Admin `/admin` (ADMIN role, enforced server-side)
`GET /users` · `PATCH /users/{id}` `{is_active?, role?}` · `GET /usage` · `GET /health` · `GET/PUT /scoring-config` · `GET/PUT /ai-config` · `PUT /usage-limits` · `GET /audit-logs`

## Health
`GET /health` (liveness) · `GET /health/ready` (DB + public AI status), also under `/api/v1`.

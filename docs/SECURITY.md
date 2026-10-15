# Security

## Controls implemented

| Area | Control |
| --- | --- |
| Passwords | Argon2id (argon2-cffi defaults); strength rules; timing-equalised verification; rehash on parameter change |
| Sessions | 15-minute JWT access tokens (HS256, `exp`/`sub`/`type` required); opaque refresh tokens stored as SHA-256 hashes, rotated on use, **reuse revokes the whole family**; logout and password change revoke sessions |
| Cookies | `HttpOnly` access/refresh cookies, refresh cookie scoped to `/api/v1/auth`, `Secure` required in production, `SameSite=lax` |
| CSRF | Double-submit token (`bg_csrf` cookie + `X-CSRF-Token` header, constant-time compare) on every cookie-authenticated state change, including refresh |
| Enumeration | Generic login errors; forgot-password always returns the same message |
| Authorization | Every user-owned query filters by `user_id`; other users' records return 404; admin checks are server-side dependencies |
| Admin privacy | Admin APIs return account metadata and aggregates only, never proposals, jobs, portfolios or resumes; admins can't deactivate or demote themselves; admin actions are audited |
| Rate limiting | Auth endpoints 10/min, AI endpoints 20/min per user/IP; per-user daily AI quota (admin-configurable) |
| Validation | Pydantic schemas with length/range limits on every field; control-character stripping; URL scheme checks; Decimal money |
| SQL injection | SQLAlchemy parameterised queries only |
| XSS | React escaping; extension content UI escapes all text; strict CSP on the SPA (nginx) and API |
| Uploads | Size limit enforced while reading; extension **and** magic-byte checks; DOCX structure and zip-bomb checks; in-memory processing; optional retention with `0600` files; deletion endpoint |
| Headers | nosniff, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, COOP, CSP, HSTS (prod), `Cache-Control: no-store` on API |
| CORS | Allow-list (`FRONTEND_URL` + `CORS_EXTRA_ORIGINS`) with credentials |
| Secrets | Environment only; production start-up validation; never returned by admin APIs; log redaction of tokens, keys, cookies and passwords |
| Audit | Registration, logins (incl. failures), password changes/resets, account deletion, admin changes |
| Privacy | JSON data export; account deletion cascades rows, files and vectors |
| Prompt injection | Untrusted text isolated as data, deterministic scoring, schema-validated outputs, no model tools |
| Extension | Minimal permissions, validated messages and senders, no secrets, closed shadow DOM, user-triggered only |

## Known limitations

1. **In-process rate limiter and background tasks.** These are correct for one backend instance. For several replicas, put the limiter behind Redis (or enforce it at the gateway) and move `auto_analyze_jobs` to a worker queue.
2. **Access tokens can't be revoked before expiry** (15 minutes max). Deactivating a user blocks them immediately, because each request reloads the user.
3. **Email** is required for production password resets. Without SMTP, reset links are only logged in non-production environments.
4. **Extension token storage:** `chrome.storage.local` isn't encrypted at rest by Chrome. Refresh tokens are rotated and revocable.
5. **No MFA** yet.
6. **Fabrication checks are heuristic.** Users must review proposals.
7. Dependency and container scanning (e.g. `pip-audit`, `npm audit`, Trivy) should run in CI.

## Reporting

Report vulnerabilities privately to the repository owner. Do not open public issues for security bugs.

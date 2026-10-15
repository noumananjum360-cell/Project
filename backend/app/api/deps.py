"""Shared FastAPI dependencies: database session, authentication, CSRF, roles."""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError
from app.db.session import get_db
from app.models import Role, User
from app.security.rate_limit import ai_rate_limit
from app.security.tokens import decode_access_token

ACCESS_COOKIE = "bg_access"
REFRESH_COOKIE = "bg_refresh"
CSRF_COOKIE = "bg_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DbSession = Annotated[Session, Depends(get_db)]


def _extract_token(request: Request) -> tuple[str | None, bool]:
    """Return (token, from_cookie)."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    cookie = request.cookies.get(ACCESS_COOKIE)
    return (cookie, True) if cookie else (None, False)


def verify_csrf(request: Request) -> None:
    """Double-submit cookie check for cookie-authenticated, state-changing requests."""
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise ForbiddenError("CSRF validation failed.", code="csrf_failed")


def get_current_user(request: Request, db: DbSession) -> User:
    token, from_cookie = _extract_token(request)
    if not token:
        raise AuthError("Not authenticated.")
    payload = decode_access_token(token)
    if from_cookie and request.method not in SAFE_METHODS:
        verify_csrf(request)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise AuthError("Invalid authentication credentials.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("Invalid authentication credentials.")
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise ForbiddenError("Administrator access required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_ai_user(request: Request, user: CurrentUser) -> User:
    """Authenticated user subject to the AI endpoint rate limit."""
    ai_rate_limit(request)
    return user


AIUser = Annotated[User, Depends(get_ai_user)]


def cookie_kwargs() -> dict[str, object]:
    s = get_settings()
    return {"secure": s.COOKIE_SECURE, "samesite": s.COOKIE_SAMESITE, "domain": s.COOKIE_DOMAIN}

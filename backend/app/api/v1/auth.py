from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    DbSession,
    cookie_kwargs,
    verify_csrf,
)
from app.core.config import get_settings
from app.core.errors import AuthError
from app.schemas.auth import (
    AccountUpdateIn,
    AuthResponse,
    ForgotPasswordIn,
    LoginIn,
    PasswordChangeIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)
from app.schemas.common import Message
from app.security.rate_limit import auth_rate_limit
from app.services import auth_service
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_PATH = "/api/v1/auth"


def _set_session_cookies(response: Response, access: str, refresh: str) -> str:
    s = get_settings()
    kw = cookie_kwargs()
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(ACCESS_COOKIE, access, httponly=True, max_age=s.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/", **kw)  # type: ignore[arg-type]
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        max_age=s.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=REFRESH_PATH,
        **kw,  # type: ignore[arg-type]
    )
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, max_age=s.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/", **kw)  # type: ignore[arg-type]
    return csrf


def _clear_session_cookies(response: Response) -> None:
    kw = {"domain": get_settings().COOKIE_DOMAIN}
    response.delete_cookie(ACCESS_COOKIE, path="/", **kw)  # type: ignore[arg-type]
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **kw)  # type: ignore[arg-type]
    response.delete_cookie(CSRF_COOKIE, path="/", **kw)  # type: ignore[arg-type]


def _token_out(access: str, refresh: str) -> TokenOut:
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_rate_limit)]
)
def register(body: RegisterIn, request: Request, response: Response, db: DbSession) -> AuthResponse:
    """Create an account and start a browser session."""
    user = auth_service.register_user(db, body.email, body.password, body.full_name)
    access, refresh = auth_service.issue_tokens(db, user, "web")
    audit(db, "auth.register", actor_id=user.id, target_type="user", target_id=user.id, request=request)
    auth_service.send_verification_email(db, user)
    db.commit()
    csrf = _set_session_cookies(response, access, refresh)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> AuthResponse:
    """Sign in. Web clients receive HttpOnly cookies; the extension client receives tokens in the body."""
    try:
        user = auth_service.authenticate(db, body.email, body.password)
    except AuthError:
        audit(db, "auth.login_failed", actor_id=None, request=request, details={"client": body.client})
        db.commit()
        raise
    access, refresh = auth_service.issue_tokens(db, user, body.client)
    audit(
        db,
        "auth.login",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        request=request,
        details={"client": body.client},
    )
    db.commit()
    if body.client == "extension":
        return AuthResponse(user=UserOut.model_validate(user), tokens=_token_out(access, refresh))
    csrf = _set_session_cookies(response, access, refresh)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/refresh", response_model=AuthResponse, dependencies=[Depends(auth_rate_limit)])
def refresh(request: Request, response: Response, db: DbSession, body: RefreshIn | None = None) -> AuthResponse:
    """Rotate the refresh token (cookie for web, body for the extension)."""
    raw = body.refresh_token if body and body.refresh_token else None
    from_cookie = raw is None
    if from_cookie:
        raw = request.cookies.get(REFRESH_COOKIE)
        if raw:
            verify_csrf(request)
    if not raw:
        raise AuthError("Not authenticated.", code="refresh_invalid")
    user, access, new_refresh, client = auth_service.rotate_refresh_token(db, raw)
    db.commit()
    if not from_cookie:
        return AuthResponse(user=UserOut.model_validate(user), tokens=_token_out(access, new_refresh))
    csrf = _set_session_cookies(response, access, new_refresh)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: DbSession, body: RefreshIn | None = None) -> Message:
    """Revoke the current refresh token and clear cookies."""
    raw = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    auth_service.revoke_refresh_token(db, raw)
    db.commit()
    _clear_session_cookies(response)
    return Message(message="Signed out.")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: AccountUpdateIn, user: CurrentUser, db: DbSession) -> UserOut:
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.onboarding_completed is not None:
        user.onboarding_completed = body.onboarding_completed
    db.commit()
    return UserOut.model_validate(user)


@router.get("/session", response_model=AuthResponse)
def session(request: Request, response: Response, user: CurrentUser) -> AuthResponse:
    """Return the current user and the CSRF token (re-issued if the cookie is missing)."""
    csrf = request.cookies.get(CSRF_COOKIE)
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, path="/", **cookie_kwargs())  # type: ignore[arg-type]
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/change-password", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def change_password(body: PasswordChangeIn, request: Request, response: Response, user: CurrentUser, db: DbSession) -> Message:
    auth_service.change_password(db, user, body.current_password, body.new_password)
    audit(db, "auth.password_changed", actor_id=user.id, target_type="user", target_id=user.id, request=request)
    access, refresh = auth_service.issue_tokens(db, user, "web")
    db.commit()
    _set_session_cookies(response, access, refresh)
    return Message(message="Password updated. Other sessions have been signed out.")


@router.post("/forgot-password", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def forgot_password(body: ForgotPasswordIn, db: DbSession) -> Message:
    auth_service.start_password_reset(db, body.email)
    db.commit()
    return Message(message="If an account exists for that email, a reset link has been sent.")


@router.post("/reset-password", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def reset_password(body: ResetPasswordIn, request: Request, db: DbSession) -> Message:
    user = auth_service.complete_password_reset(db, body.token, body.new_password)
    audit(db, "auth.password_reset", actor_id=user.id, target_type="user", target_id=user.id, request=request)
    db.commit()
    return Message(message="Password has been reset. Please sign in.")


@router.post("/verify-email", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def verify_email(body: VerifyEmailIn, db: DbSession) -> Message:
    auth_service.verify_email(db, body.token)
    db.commit()
    return Message(message="Email verified.")


@router.post("/resend-verification", response_model=Message, dependencies=[Depends(auth_rate_limit)])
def resend_verification(user: CurrentUser, db: DbSession) -> Message:
    if user.email_verified_at is None:
        auth_service.send_verification_email(db, user)
        db.commit()
    return Message(message="If your email is unverified, a new verification link has been sent.")

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ConflictError
from app.core.logging import get_logger
from app.models import RefreshToken, User, UserPreferences, UserProfile, UserToken
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import create_access_token, hash_token, new_opaque_token
from app.services.email import send_email

log = get_logger(__name__)

PURPOSE_RESET = "password_reset"
PURPOSE_VERIFY = "email_verification"


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, password: str, full_name: str | None) -> User:
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("An account with this email already exists.", code="email_taken")
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id, full_name=full_name))
    db.add(UserPreferences(user_id=user.id))
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # verify_password always runs a hash comparison to avoid timing-based enumeration.
    ok = verify_password(password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        raise AuthError("Invalid email or password.", code="invalid_credentials")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    return user


def issue_tokens(db: Session, user: User, client: str = "web", family_id: uuid.UUID | None = None) -> tuple[str, str]:
    settings = get_settings()
    refresh = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            family_id=family_id or uuid.uuid4(),
            client=client,
            expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return create_access_token(user.id, user.role), refresh


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str, str, str]:
    """Rotate a refresh token. Reuse of a revoked token revokes the whole family."""
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if record is None:
        raise AuthError("Session expired. Please sign in again.", code="refresh_invalid")
    if record.revoked_at is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        db.commit()
        log.warning("refresh_token_reuse_detected", user_id=str(record.user_id))
        raise AuthError("Session expired. Please sign in again.", code="refresh_invalid")
    if record.expires_at < _now():
        raise AuthError("Session expired. Please sign in again.", code="refresh_invalid")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("Session expired. Please sign in again.", code="refresh_invalid")
    record.revoked_at = _now()
    access, refresh = issue_tokens(db, user, record.client, record.family_id)
    return user, access, refresh, record.client


def revoke_refresh_token(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=_now())
    )


def _create_user_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    raw = new_opaque_token()
    db.add(UserToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=_now() + ttl))
    return raw


def _consume_user_token(db: Session, raw: str, purpose: str) -> User:
    record = db.scalar(select(UserToken).where(UserToken.token_hash == hash_token(raw), UserToken.purpose == purpose))
    if record is None or record.used_at is not None or record.expires_at < _now():
        raise AuthError("This link is invalid or has expired.", code="token_invalid")
    record.used_at = _now()
    user = db.get(User, record.user_id)
    if user is None:
        raise AuthError("This link is invalid or has expired.", code="token_invalid")
    return user


def start_password_reset(db: Session, email: str) -> None:
    """Always succeeds from the caller's perspective to prevent account enumeration."""
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active:
        return
    raw = _create_user_token(db, user, PURPOSE_RESET, timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES))
    link = f"{settings.FRONTEND_URL}/reset-password?token={raw}"
    send_email(
        user.email,
        "Reset your BidGenie AI password",
        f"Use this link to reset your password (valid {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes):\n{link}\n\n"
        "If you did not request this, you can ignore this email.",
        dev_link=link,
    )


def complete_password_reset(db: Session, raw: str, new_password: str) -> User:
    user = _consume_user_token(db, raw, PURPOSE_RESET)
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
    return user


def send_verification_email(db: Session, user: User) -> None:
    settings = get_settings()
    raw = _create_user_token(db, user, PURPOSE_VERIFY, timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS))
    link = f"{settings.FRONTEND_URL}/verify-email?token={raw}"
    send_email(user.email, "Verify your BidGenie AI email", f"Confirm your email address:\n{link}", dev_link=link)


def verify_email(db: Session, raw: str) -> User:
    user = _consume_user_token(db, raw, PURPOSE_VERIFY)
    user.email_verified_at = user.email_verified_at or _now()
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthError("Current password is incorrect.", code="invalid_credentials")
    user.password_hash = hash_password(new)
    revoke_all_sessions(db, user.id)

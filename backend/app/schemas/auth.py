from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


def _password_strength(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if v.lower() == v or v.upper() == v or not any(c.isdigit() for c in v):
        raise ValueError("Password must include upper- and lower-case letters and a number.")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    full_name: str | None = Field(default=None, max_length=200)

    _pw = field_validator("password")(_password_strength)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    client: Literal["web", "extension"] = "web"


class RefreshIn(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    email_verified_at: datetime | None
    onboarding_completed: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str | None = None
    tokens: TokenOut | None = None  # only for the browser extension client


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)

    _pw = field_validator("new_password")(_password_strength)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=128)

    _pw = field_validator("new_password")(_password_strength)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class AccountUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    onboarding_completed: bool | None = None


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=128)

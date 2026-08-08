from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token scheme, not a secret
    expires_in: int

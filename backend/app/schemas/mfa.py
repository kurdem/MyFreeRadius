"""MFA (TOTP) schemas."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@\-]{1,128}$")
_MODES = {"totp_only", "ad_password_plus_totp"}


class EnrollRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("username contains invalid characters")
        return v


class EnrollResponse(BaseModel):
    username: str
    secret: str
    otpauth_uri: str


class ConfirmRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=8)


class TokenOut(BaseModel):
    username: str
    confirmed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MfaSettings(BaseModel):
    mfa_enabled: bool
    mfa_mode: str = "totp_only"

    @field_validator("mfa_mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        if v not in _MODES:
            raise ValueError(f"mfa_mode must be one of: {', '.join(sorted(_MODES))}")
        return v


class RadiusAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(default="", max_length=256)
    token: str = Field(min_length=1, max_length=256)


class TestAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username", "password")
    @classmethod
    def _no_control(cls, v: str) -> str:
        # Values are placed into a radclient attribute line; reject anything that
        # could break out of the quoted token or inject a second attribute.
        if any(c in v for c in ('"', "\\", "\n", "\r")):
            raise ValueError("must not contain quotes, backslashes or newlines")
        return v


class TestAuthResult(BaseModel):
    result: str
    duration_ms: int
    details: str | None = None
    accepted: bool = False

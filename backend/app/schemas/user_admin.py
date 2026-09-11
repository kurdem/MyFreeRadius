"""Schemas for local user administration (issue #7)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from app.models import UserRole

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@\-]{1,64}$")


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    role: UserRole = UserRole.OPERATOR

    @field_validator("username")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("username may only contain letters, digits, . _ - @")
        return v


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)

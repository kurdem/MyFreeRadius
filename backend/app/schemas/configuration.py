"""Configuration lifecycle schemas (spec sections 15, 16)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models import ConfigState


class ConfigVersionOut(BaseModel):
    id: int
    version: int
    state: ConfigState
    checksum: str
    change_summary: str | None
    author: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationResult(BaseModel):
    valid: bool
    message: str
    details: str | None = None


class ApplyResult(BaseModel):
    success: bool
    message: str
    version: int | None = None
    details: str | None = None

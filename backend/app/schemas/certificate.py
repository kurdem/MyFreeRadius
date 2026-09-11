"""CA certificate schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CertUpload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pem: str = Field(min_length=1, max_length=100_000)


class CertOut(BaseModel):
    id: int
    name: str
    subject: str
    issuer: str
    fingerprint_sha256: str
    not_before: datetime
    not_after: datetime
    status: str
    days_left: int

    model_config = {"from_attributes": True}

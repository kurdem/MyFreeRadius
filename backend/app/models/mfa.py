"""TOTP multi-factor authentication (Phase 4).

A per-user TOTP secret (encrypted at rest). Only *confirmed* tokens are used for
authentication, so enrollment requires the user to prove they can generate a
valid code before MFA is enforced for them.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserTotp(Base, TimestampMixin):
    __tablename__ = "user_totp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # AD logon name (sAMAccountName), lower-cased for stable matching.
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

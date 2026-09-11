"""Versioned FreeRADIUS configuration snapshots (spec sections 15, 16).

Every generated ``clients.conf`` is stored as an immutable version so that we
can show history, diff, and roll back. Exactly one version is ACTIVE at a time.
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ConfigState(str, enum.Enum):
    PENDING = "pending"      # generated, not yet activated
    ACTIVE = "active"        # currently loaded by FreeRADIUS
    PREVIOUS = "previous"    # superseded but retained for rollback
    FAILED = "failed"        # validation or apply failed


class ConfigVersion(Base, TimestampMixin):
    __tablename__ = "config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Monotonically increasing, human-facing version number.
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    state: Mapped[ConfigState] = mapped_column(
        Enum(ConfigState, native_enum=False, length=16),
        default=ConfigState.PENDING,
        nullable=False,
    )
    # The generated clients.conf content (secrets appear here in cleartext because
    # FreeRADIUS needs them; this table lives in the DB volume, never exported).
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256 of the content for integrity / dedupe.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)

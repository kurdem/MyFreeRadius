"""Local web-interface user accounts and roles (spec sections 21, 22)."""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """RBAC roles.

    * ADMINISTRATOR - full access.
    * OPERATOR       - view + run tests, no critical changes.
    * AUDITOR        - read-only: logs, history, reports.
    """

    ADMINISTRATOR = "administrator"
    OPERATOR = "operator"
    AUDITOR = "auditor"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Argon2id hash - never the plaintext password.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32), default=UserRole.ADMINISTRATOR, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Login lockout tracking (spec section 21).
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[str | None] = mapped_column(String(64), nullable=True)

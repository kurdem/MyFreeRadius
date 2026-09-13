"""Authentication policies (Phase 7).

An ordered, first-match policy engine that maps a request's RADIUS client group
and the user's AD group membership to an allow/deny decision plus optional RADIUS
reply attributes. Evaluated in the backend authorize path (rlm_rest).

Matching (all present conditions must hold):
  * ``client_group_id is None``  -> matches any client group;
  * ``ad_group_dn is None``      -> matches any AD group;
otherwise the request's client group must equal ``client_group_id`` and the
user's group DNs must contain ``ad_group_dn`` (case-insensitive).

Rules are evaluated by ascending ``priority`` (then id); the first matching,
enabled rule decides. Reply attributes are applied only on an ALLOW.
"""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PolicyAction(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class AuthPolicy(Base, TimestampMixin):
    __tablename__ = "auth_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Lower priority is evaluated first (first match wins).
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # None => any client group.
    client_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_groups.id", ondelete="CASCADE"), nullable=True
    )
    # None => any AD group. DN stored plus a human label for the UI.
    ad_group_dn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ad_group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=8),
        default=PolicyAction.ALLOW,
        nullable=False,
    )
    # JSON list of {"name": "...", "value": "..."} RADIUS reply attributes,
    # applied on ALLOW. Stored as text for portability across SQLite/Postgres.
    reply_attributes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

"""RADIUS clients and client groups (spec sections 4, 5)."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ClientGroup(Base, TimestampMixin):
    """A named group of RADIUS clients, e.g. a Horizon Connection Server cluster."""

    __tablename__ = "client_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    clients: Mapped[list["RadiusClient"]] = relationship(
        back_populates="group", cascade="save-update"
    )


class RadiusClient(Base, TimestampMixin):
    """A RADIUS client (NAS), e.g. a Horizon Connection Server.

    The shared secret is stored encrypted at rest (Fernet) in
    ``shared_secret_encrypted`` and never returned in plaintext through the API.
    """

    __tablename__ = "radius_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    # Stored as CIDR or single IP, validated in the schema layer.
    ipaddr: Mapped[str] = mapped_column(String(64), nullable=False)
    shared_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # "other" is the safe FreeRADIUS default; "vmware" documents intent for Horizon.
    nas_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Comma-separated tags, kept simple for phase 2.
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_groups.id", ondelete="SET NULL"), nullable=True
    )
    group: Mapped[ClientGroup | None] = relationship(back_populates="clients")

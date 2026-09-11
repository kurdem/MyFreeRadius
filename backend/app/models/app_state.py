"""Singleton application state (e.g. first-run setup completion)."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AppState(Base, TimestampMixin):
    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

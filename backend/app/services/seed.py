"""First-start bootstrap: create tables and the initial administrator."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Base, User, UserRole
from app.security.passwords import hash_password

logger = logging.getLogger("startup")


def init_db() -> None:
    """Create tables if they do not exist.

    Phase 1/2 uses ``create_all``; an Alembic migration chain can replace this
    once the schema stabilises (a migrations dir is included for that purpose).
    """
    Base.metadata.create_all(bind=engine)


def bootstrap_admin() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_password:
        logger.warning(
            "startup", extra={"event": "bootstrap_skipped",
                              "result": "no BOOTSTRAP_ADMIN_PASSWORD set"}
        )
        return
    db: Session = SessionLocal()
    try:
        existing = db.scalar(select(User).limit(1))
        if existing is not None:
            return
        admin = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role=UserRole.ADMINISTRATOR,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logger.info(
            "startup",
            extra={"event": "bootstrap_admin_created", "user": admin.username},
        )
    finally:
        db.close()

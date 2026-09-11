"""First-start bootstrap: create tables and the initial administrator."""
from __future__ import annotations

import logging

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Base, User, UserRole
from app.security.passwords import hash_password

logger = logging.getLogger("startup")


# Lightweight additive migrations for columns added after a table already exists.
# Keyed by table name. `create_all` never ALTERs existing tables, so new columns
# on existing installs are added here. Values: (column_name, DDL type + default).
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "radius_clients": [
        ("require_message_authenticator", "BOOLEAN NOT NULL DEFAULT {false}"),
    ],
}


def _apply_additive_migrations() -> None:
    """Add columns introduced after initial release, idempotently (SQLite/PG)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    # Dialect-appropriate boolean false literal.
    false_literal = "0" if engine.dialect.name == "sqlite" else "false"

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all already made it with all columns
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name in present:
                    continue
                col_ddl = ddl.format(false=false_literal)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_ddl}"))
                logger.info(
                    "startup",
                    extra={"event": "migration_add_column", "object": f"{table}.{name}"},
                )


def init_db() -> None:
    """Create tables if they do not exist, then apply additive migrations.

    Phase 1/2/3 uses ``create_all`` plus a tiny additive-column migration; an
    Alembic migration chain can replace this once the schema stabilises.
    """
    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()


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

"""Audit logging helper (spec section 23)."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger("audit")


def record(
    db: Session,
    *,
    username: str | None,
    action: str,
    object_ref: str | None = None,
    source_ip: str | None = None,
    result: str = "SUCCESS",
    detail: str | None = None,
) -> None:
    """Persist an audit entry and emit a structured log line.

    Callers must never pass secrets in ``detail``.
    """
    entry = AuditLog(
        username=username,
        action=action,
        object_ref=object_ref,
        source_ip=source_ip,
        result=result,
        detail=detail,
    )
    db.add(entry)
    db.commit()
    logger.info(
        "audit",
        extra={
            "event": "audit",
            "user": username,
            "action": action,
            "object": object_ref,
            "client_ip": source_ip,
            "result": result,
        },
    )

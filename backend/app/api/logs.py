"""RADIUS live log and audit log endpoints (spec sections 13, 23)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User
from app.security.deps import require_any
from app.services import radius_agent
from app.services.radius_agent import AgentError

router = APIRouter(tags=["logs"])


@router.get("/logs/radius")
def radius_logs(
    limit: int = Query(default=200, ge=1, le=2000),
    _: User = Depends(require_any),
):
    """Tail of the FreeRADIUS log. Secrets are masked by the control agent."""
    try:
        return radius_agent.logs(limit=limit)
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/logs/auth-events")
def auth_events(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_any),
):
    """Recent authentication attempts with the reject reason (issue #8).

    MFA / AD authorization runs in the backend, so the reason a login failed
    (invalid OTP, not in an allowed AD group, invalid AD password, …) is recorded
    in the audit log. This surfaces those results as a focused feed.
    """
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.action.in_(("RADIUS_AUTHORIZE", "RADIUS_TEST")))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "timestamp": r.created_at.isoformat(),
            # For a test the authenticated subject is in object_ref (username is
            # the operator who ran it); for a real request username is the subject.
            "username": r.object_ref if r.action == "RADIUS_TEST" else r.username,
            "source": "test" if r.action == "RADIUS_TEST" else "radius",
            "result": r.result,
            "reason": r.detail,
            "source_ip": r.source_ip,
        }
        for r in rows
    ]


@router.get("/logs/audit")
def audit_logs(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_any),
):
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "timestamp": r.created_at.isoformat(),
            "username": r.username,
            "action": r.action,
            "object": r.object_ref,
            "source_ip": r.source_ip,
            "result": r.result,
            "detail": r.detail,
        }
        for r in rows
    ]

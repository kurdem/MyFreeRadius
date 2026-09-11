"""Configuration lifecycle endpoints (spec sections 15, 16).

Workflow exposed to the UI:

    generate (pending) -> validate -> activate
                                   \-> rollback (to previous)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConfigVersion, User
from app.schemas.configuration import ApplyResult, ConfigVersionOut, ValidationResult
from app.security.deps import require_admin, require_any
from app.services import audit, configuration
from app.services.radius_agent import AgentError

router = APIRouter(prefix="/configuration", tags=["configuration"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/history", response_model=list[ConfigVersionOut])
def history(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_any),
):
    versions = db.scalars(
        select(ConfigVersion).order_by(ConfigVersion.version.desc()).limit(limit)
    ).all()
    return versions


@router.get("/pending", response_model=ConfigVersionOut | None)
def generate_pending(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Render current DB state into a candidate (PENDING) configuration."""
    version = configuration.generate_pending(db, author=user.username)
    return version


@router.get("/{version_id}/content")
def get_content(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_any),
):
    """Return raw config text for diff/preview.

    Note: this contains shared secrets in cleartext (FreeRADIUS requires them),
    so it is restricted to authenticated users and never exported by default.
    """
    version = db.get(ConfigVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found")
    return {"version": version.version, "content": version.content}


@router.post("/{version_id}/validate", response_model=ValidationResult)
def validate(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    version = db.get(ConfigVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found")
    try:
        result = configuration.validate(version)
    except AgentError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return ValidationResult(
        valid=bool(result.get("valid")),
        message=result.get("message", ""),
        details=result.get("details"),
    )


@router.post("/{version_id}/activate", response_model=ApplyResult)
def activate(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    version = db.get(ConfigVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found")
    try:
        result = configuration.activate(db, version)
    except AgentError as exc:
        audit.record(
            db, username=user.username, action="ACTIVATE_CONFIG",
            object_ref=f"v{version.version}", source_ip=_client_ip(request),
            result="FAILURE", detail=str(exc)[:200],
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    audit.record(
        db, username=user.username, action="ACTIVATE_CONFIG",
        object_ref=f"v{version.version}", source_ip=_client_ip(request),
        result="SUCCESS" if result.get("success") else "FAILURE",
    )
    return ApplyResult(
        success=bool(result.get("success")),
        message=result.get("message", ""),
        version=version.version,
        details=result.get("details"),
    )


@router.post("/rollback", response_model=ApplyResult)
def rollback(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        restored = configuration.rollback(db, author=user.username)
    except (configuration.ConfigError, AgentError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit.record(
        db, username=user.username, action="ROLLBACK_CONFIG",
        object_ref=f"v{restored.version}", source_ip=_client_ip(request),
    )
    return ApplyResult(success=True, message="Rolled back", version=restored.version)

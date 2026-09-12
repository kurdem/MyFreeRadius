"""Configuration lifecycle endpoints (spec sections 15, 16).

Workflow exposed to the UI:

    generate (pending) -> validate -> activate
                                   -> rollback / restore (to an earlier version)
                                   -> delete (remove a stored version)
"""
from __future__ import annotations

import json

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
    """Return the config bundle (files + deletes) for diff/preview.

    Note: this contains secrets in cleartext (FreeRADIUS requires them), so it
    is restricted to authenticated users and never exported by default.
    """
    version = db.get(ConfigVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found")
    try:
        bundle = json.loads(version.content)
    except (ValueError, TypeError):
        # Legacy single-file content stored before the bundle format.
        bundle = {"files": {"clients.conf": version.content}, "deletes": []}
    return {
        "version": version.version,
        "files": bundle.get("files", {}),
        "deletes": bundle.get("deletes", []),
    }


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


@router.post("/{version_id}/restore", response_model=ApplyResult)
def restore(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Re-activate a specific historical version (append + activate)."""
    try:
        restored = configuration.restore(db, version_id=version_id, author=user.username)
    except configuration.ConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AgentError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    audit.record(
        db, username=user.username, action="RESTORE_CONFIG",
        object_ref=f"v{restored.version}", source_ip=_client_ip(request),
    )
    return ApplyResult(success=True, message="Restored", version=restored.version)


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Delete a stored configuration version (the active one is protected)."""
    try:
        number = configuration.delete_version(db, version_id=version_id)
    except configuration.ConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    audit.record(
        db, username=user.username, action="DELETE_CONFIG",
        object_ref=f"v{number}", source_ip=_client_ip(request),
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

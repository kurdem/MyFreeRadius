"""Backup / restore endpoints (spec section 17)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security.deps import require_admin
from app.services import audit, backup_service

router = APIRouter(prefix="/backup", tags=["backup"])

_MAX_BACKUP_BYTES = 20_000_000


class ExportRequest(BaseModel):
    passphrase: str | None = Field(default=None, max_length=256)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/export")
def export_backup(
    payload: ExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Download a full configuration backup (optionally passphrase-encrypted)."""
    blob = backup_service.serialize(db, passphrase=payload.passphrase or None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = "enc.json" if payload.passphrase else "json"
    filename = f"freeradius-manager-backup-{stamp}.{suffix}"
    audit.record(
        db, username=user.username, action="BACKUP_EXPORT",
        source_ip=_client_ip(request),
        detail="encrypted" if payload.passphrase else "plain",
    )
    return Response(
        content=blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(
    request: Request,
    file: UploadFile = File(...),
    passphrase: str = Form(""),
    force: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Restore configuration from an uploaded backup file (DESTRUCTIVE).

    Replaces clients, groups, AD config/groups, MFA tokens, certificates and
    local users with the backup content.
    """
    raw = await file.read(_MAX_BACKUP_BYTES + 1)
    if len(raw) > _MAX_BACKUP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Backup file too large")
    try:
        data = backup_service.deserialize(raw, passphrase=passphrase or None)
        counts = backup_service.restore(db, data, force=force)
    except backup_service.BackupError as exc:
        audit.record(
            db, username=user.username, action="BACKUP_RESTORE",
            source_ip=_client_ip(request), result="FAILURE", detail=str(exc)[:200],
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    audit.record(
        db, username=user.username, action="BACKUP_RESTORE",
        source_ip=_client_ip(request),
        detail=", ".join(f"{k}={v}" for k, v in counts.items()),
    )
    return {
        "message": "Configuration restored. Generate & activate the configuration "
                   "to apply it to FreeRADIUS. You may need to log in again.",
        "restored": counts,
    }

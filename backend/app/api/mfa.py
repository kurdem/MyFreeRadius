"""MFA (TOTP) management endpoints (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ADConfig, User, UserTotp
from app.schemas.mfa import (
    ConfirmRequest,
    EnrollRequest,
    EnrollResponse,
    MfaSettings,
    TokenOut,
)
from app.security.deps import require_admin, require_any
from app.services import audit, totp_service

router = APIRouter(prefix="/mfa", tags=["mfa"])

_ISSUER = "FreeRADIUS Manager"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/settings", response_model=MfaSettings)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_any)):
    cfg = db.get(ADConfig, 1)
    if cfg is None:
        return MfaSettings(mfa_enabled=False, mfa_mode="totp_only")
    return MfaSettings(mfa_enabled=cfg.mfa_enabled, mfa_mode=cfg.mfa_mode)


@router.put("/settings", response_model=MfaSettings)
def put_settings(
    payload: MfaSettings,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    cfg = db.get(ADConfig, 1)
    if cfg is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Configure Active Directory before enabling MFA",
        )
    cfg.mfa_enabled = payload.mfa_enabled
    cfg.mfa_mode = payload.mfa_mode
    db.commit()
    audit.record(
        db, username=user.username, action="UPDATE_MFA_SETTINGS",
        object_ref=payload.mfa_mode, source_ip=_client_ip(request),
        detail=f"enabled={payload.mfa_enabled}",
    )
    return MfaSettings(mfa_enabled=cfg.mfa_enabled, mfa_mode=cfg.mfa_mode)


@router.post("/enroll", response_model=EnrollResponse)
def enroll(
    payload: EnrollRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Create (or replace) a pending TOTP secret for a user and return the URI.

    The token is unconfirmed until the user proves a valid code via /confirm.
    """
    secret = totp_service.new_secret()
    existing = db.scalar(
        select(UserTotp).where(func.lower(UserTotp.username) == payload.username.lower())
    )
    if existing is None:
        existing = UserTotp(username=payload.username.lower())
        db.add(existing)
    existing.secret_encrypted = totp_service.encrypt(secret)
    existing.confirmed = False
    db.commit()
    audit.record(
        db, username=user.username, action="MFA_ENROLL",
        object_ref=payload.username, source_ip=_client_ip(request),
    )
    return EnrollResponse(
        username=payload.username.lower(),
        secret=secret,
        otpauth_uri=totp_service.provisioning_uri(secret, payload.username, _ISSUER),
    )


@router.post("/confirm")
def confirm(
    payload: ConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    token = db.scalar(
        select(UserTotp).where(func.lower(UserTotp.username) == payload.username.lower())
    )
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No enrollment for this user")
    if not totp_service.verify(token.secret_encrypted, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    token.confirmed = True
    db.commit()
    audit.record(
        db, username=user.username, action="MFA_CONFIRM",
        object_ref=payload.username, source_ip=_client_ip(request),
    )
    return {"message": "MFA token confirmed"}


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(db: Session = Depends(get_db), _: User = Depends(require_any)):
    return db.scalars(select(UserTotp).order_by(UserTotp.username)).all()


@router.delete("/tokens/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_token(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    token = db.scalar(
        select(UserTotp).where(func.lower(UserTotp.username) == username.lower())
    )
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Token not found")
    db.delete(token)
    db.commit()
    audit.record(
        db, username=user.username, action="MFA_DELETE_TOKEN",
        object_ref=username, source_ip=_client_ip(request),
    )

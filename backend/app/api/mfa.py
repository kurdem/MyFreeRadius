"""MFA (TOTP) management endpoints (Phase 4)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ADConfig, MfaEnrollmentToken, User, UserTotp
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
_LINK_TTL_HOURS = 24
_MAX_CONFIRM_ATTEMPTS = 10


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


# --------------------------------------------------------------------------- #
# Self-service enrollment links (issue #11)
# --------------------------------------------------------------------------- #
class EnrollLinkResponse(BaseModel):
    token: str
    username: str
    expires_at: datetime
    enroll_path: str


class SelfEnrollInfo(BaseModel):
    username: str
    otpauth_uri: str
    secret: str


@router.post("/enroll-link", response_model=EnrollLinkResponse)
def create_enroll_link(
    payload: EnrollRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Create a single-use, time-limited self-service enrollment link."""
    token = secrets.token_urlsafe(32)
    secret = totp_service.new_secret()
    row = MfaEnrollmentToken(
        token=token,
        username=payload.username.lower(),
        secret_encrypted=totp_service.encrypt(secret),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=_LINK_TTL_HOURS),
    )
    db.add(row)
    db.commit()
    audit.record(
        db, username=user.username, action="MFA_ENROLL_LINK",
        object_ref=payload.username, source_ip=_client_ip(request),
    )
    return EnrollLinkResponse(
        token=token, username=row.username, expires_at=row.expires_at,
        enroll_path=f"/enroll/{token}",
    )


def _valid_token(db: Session, token: str) -> MfaEnrollmentToken:
    row = db.scalar(select(MfaEnrollmentToken).where(MfaEnrollmentToken.token == token))
    if row is None or row.used:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This enrollment link is invalid or already used")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, detail="This enrollment link has expired")
    return row


# NOTE: the two endpoints below are intentionally PUBLIC (no session/CSRF) so a
# user can self-enroll from a link. The random token is the credential.
@router.get("/enroll/{token}", response_model=SelfEnrollInfo)
def self_enroll_info(token: str, db: Session = Depends(get_db)):
    row = _valid_token(db, token)
    from app.security.crypto import decrypt_secret

    secret = decrypt_secret(row.secret_encrypted)
    return SelfEnrollInfo(
        username=row.username,
        secret=secret,
        otpauth_uri=totp_service.provisioning_uri(secret, row.username, _ISSUER),
    )


class SelfConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/enroll/{token}/confirm")
def self_enroll_confirm(
    token: str,
    payload: SelfConfirm,
    request: Request,
    db: Session = Depends(get_db),
):
    row = _valid_token(db, token)
    if not totp_service.verify(row.secret_encrypted, payload.code):
        row.attempts += 1
        if row.attempts >= _MAX_CONFIRM_ATTEMPTS:
            row.used = True  # invalidate after too many wrong codes
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    # Activate the user's TOTP token and consume the link.
    existing = db.scalar(
        select(UserTotp).where(func.lower(UserTotp.username) == row.username.lower())
    )
    if existing is None:
        existing = UserTotp(username=row.username.lower())
        db.add(existing)
    existing.secret_encrypted = row.secret_encrypted
    existing.confirmed = True
    row.used = True
    db.commit()
    audit.record(
        db, username=row.username, action="MFA_SELF_ENROLLED",
        object_ref=row.username, source_ip=_client_ip(request),
    )
    return {"message": "MFA enrolled successfully"}

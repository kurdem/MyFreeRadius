"""Active Directory configuration + connection test endpoints (spec sections 6, 7).

Phase 3, slice 1: store and test the AD/LDAP connection and manage allowed
groups. Using AD to authenticate RADIUS users is wired in the next slice.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ADConfig, ADGroup, User
from app.schemas.active_directory import (
    ADConfigOut,
    ADConfigUpsert,
    ADConnectionTestResult,
    ADGroupCreate,
    ADGroupOut,
)
from app.security.crypto import encrypt_secret
from app.security.deps import require_admin, require_any, require_operator
from app.services import audit, ldap_service

router = APIRouter(prefix="/active-directory", tags=["active-directory"])

_SINGLETON_ID = 1


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_config(db: Session) -> ADConfig | None:
    return db.get(ADConfig, _SINGLETON_ID)


def _to_out(cfg: ADConfig) -> ADConfigOut:
    return ADConfigOut(
        domain=cfg.domain,
        primary_dc=cfg.primary_dc,
        secondary_dc=cfg.secondary_dc,
        port=cfg.port,
        use_ldaps=cfg.use_ldaps,
        verify_tls=cfg.verify_tls,
        base_dn=cfg.base_dn,
        bind_user=cfg.bind_user,
        timeout_seconds=cfg.timeout_seconds,
        enabled=cfg.enabled,
        configured=True,
        has_bind_password=bool(cfg.bind_password_encrypted),
    )


@router.get("", response_model=ADConfigOut | None)
def get_config(db: Session = Depends(get_db), _: User = Depends(require_any)):
    cfg = _get_config(db)
    return _to_out(cfg) if cfg else None


@router.put("", response_model=ADConfigOut)
def upsert_config(
    payload: ADConfigUpsert,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    cfg = _get_config(db)
    data = payload.model_dump(exclude={"bind_password"})

    if cfg is None:
        if not payload.bind_password:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="bind_password is required when configuring AD for the first time",
            )
        cfg = ADConfig(
            id=_SINGLETON_ID,
            bind_password_encrypted=encrypt_secret(payload.bind_password),
            **data,
        )
        db.add(cfg)
        action = "CREATE_AD_CONFIG"
    else:
        for field, value in data.items():
            setattr(cfg, field, value)
        if payload.bind_password:
            cfg.bind_password_encrypted = encrypt_secret(payload.bind_password)
        action = "UPDATE_AD_CONFIG"

    db.commit()
    db.refresh(cfg)
    audit.record(
        db, username=user.username, action=action, object_ref=cfg.domain,
        source_ip=_client_ip(request),
        detail="bind password set" if payload.bind_password else None,
    )
    return _to_out(cfg)


@router.post("/test", response_model=ADConnectionTestResult)
def test_connection(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    cfg = _get_config(db)
    if cfg is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="AD is not configured yet")
    result = ldap_service.test_connection(cfg)
    audit.record(
        db, username=user.username, action="TEST_AD_CONNECTION",
        object_ref=cfg.primary_dc, source_ip=_client_ip(request),
        result="SUCCESS" if result.get("success") else "FAILURE",
    )
    return ADConnectionTestResult(
        success=bool(result.get("success")),
        message=result.get("message", ""),
        details=result.get("details"),
    )


# --------------------------------------------------------------------------- #
# Allowed groups
# --------------------------------------------------------------------------- #
@router.get("/groups", response_model=list[ADGroupOut])
def list_groups(db: Session = Depends(get_db), _: User = Depends(require_any)):
    return db.scalars(select(ADGroup).order_by(ADGroup.name)).all()


@router.post("/groups", response_model=ADGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: ADGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if db.scalar(select(ADGroup).where(ADGroup.group_dn == payload.group_dn)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This group DN already exists")
    group = ADGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record(
        db, username=user.username, action="CREATE_AD_GROUP",
        object_ref=group.name, source_ip=_client_ip(request),
    )
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    group = db.get(ADGroup, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")
    name = group.name
    db.delete(group)
    db.commit()
    audit.record(
        db, username=user.username, action="DELETE_AD_GROUP",
        object_ref=name, source_ip=_client_ip(request),
    )

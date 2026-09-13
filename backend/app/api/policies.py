"""Authentication policy CRUD (Phase 7).

Ordered, first-match rules mapping (client group, AD group) -> allow/deny +
reply attributes. Enforced by the backend authorize path (rlm_rest). Reads are
available to any authenticated user; writes require an administrator.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthPolicy, ClientGroup, User
from app.schemas.policy import PolicyCreate, PolicyOut, PolicyUpdate
from app.security.deps import require_admin, require_any
from app.services import audit

router = APIRouter(prefix="/policies", tags=["policies"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(db: Session, p: AuthPolicy) -> PolicyOut:
    try:
        reply = json.loads(p.reply_attributes) if p.reply_attributes else []
    except (ValueError, TypeError):
        reply = []
    group_name = None
    if p.client_group_id is not None:
        cg = db.get(ClientGroup, p.client_group_id)
        group_name = cg.name if cg else None
    return PolicyOut(
        id=p.id,
        name=p.name,
        priority=p.priority,
        enabled=p.enabled,
        client_group_id=p.client_group_id,
        ad_group_dn=p.ad_group_dn,
        ad_group_name=p.ad_group_name,
        action=p.action,
        reply_attributes=reply,
        client_group_name=group_name,
    )


def _validate_group(db: Session, client_group_id: int | None) -> None:
    if client_group_id is not None and db.get(ClientGroup, client_group_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="client_group_id does not exist")


@router.get("", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db), _: User = Depends(require_any)):
    policies = db.scalars(
        select(AuthPolicy).order_by(AuthPolicy.priority.asc(), AuthPolicy.id.asc())
    ).all()
    return [_to_out(db, p) for p in policies]


@router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _validate_group(db, payload.client_group_id)
    policy = AuthPolicy(
        name=payload.name,
        priority=payload.priority,
        enabled=payload.enabled,
        client_group_id=payload.client_group_id,
        ad_group_dn=payload.ad_group_dn,
        ad_group_name=payload.ad_group_name,
        action=payload.action,
        reply_attributes=json.dumps([a.model_dump() for a in payload.reply_attributes]),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    audit.record(
        db, username=user.username, action="CREATE_POLICY",
        object_ref=policy.name, source_ip=_client_ip(request),
    )
    return _to_out(db, policy)


@router.put("/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: int,
    payload: PolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    policy = db.get(AuthPolicy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Policy not found")
    data = payload.model_dump(exclude_unset=True)
    if "client_group_id" in data:
        _validate_group(db, data["client_group_id"])
    for field in ("name", "priority", "enabled", "client_group_id", "ad_group_dn",
                  "ad_group_name", "action"):
        if field in data:
            setattr(policy, field, data[field])
    if "reply_attributes" in data:
        policy.reply_attributes = json.dumps(
            [a.model_dump() for a in payload.reply_attributes] if payload.reply_attributes else []
        )
    db.commit()
    db.refresh(policy)
    audit.record(
        db, username=user.username, action="UPDATE_POLICY",
        object_ref=policy.name, source_ip=_client_ip(request),
    )
    return _to_out(db, policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    policy = db.get(AuthPolicy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Policy not found")
    name = policy.name
    db.delete(policy)
    db.commit()
    audit.record(
        db, username=user.username, action="DELETE_POLICY",
        object_ref=name, source_ip=_client_ip(request),
    )

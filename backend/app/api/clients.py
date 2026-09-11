"""RADIUS client CRUD endpoints (spec sections 4, 5).

Changes here only update the database. They take effect in FreeRADIUS after the
configuration is generated and activated via the ``/configuration`` endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ClientGroup, RadiusClient, User
from app.schemas.client import (
    ClientCreate,
    ClientGroupCreate,
    ClientGroupOut,
    ClientOut,
    ClientUpdate,
)
from app.security.crypto import encrypt_secret
from app.security.deps import require_admin, require_any
from app.services import audit

router = APIRouter(prefix="/clients", tags=["clients"])


def _to_out(c: RadiusClient) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        ipaddr=c.ipaddr,
        nas_type=c.nas_type,
        description=c.description,
        location=c.location,
        tags=c.tags,
        enabled=c.enabled,
        require_message_authenticator=c.require_message_authenticator,
        group_id=c.group_id,
        has_secret=bool(c.shared_secret_encrypted),
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), _: User = Depends(require_any)):
    clients = db.scalars(select(RadiusClient).order_by(RadiusClient.name)).all()
    return [_to_out(c) for c in clients]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if db.scalar(select(RadiusClient).where(RadiusClient.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A client with this name exists")
    if payload.group_id is not None and not db.get(ClientGroup, payload.group_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="group_id does not exist")

    # Default the BlastRADIUS requirement from the NAS type when unspecified:
    # VMware Horizon / UAG sends a Message-Authenticator, so require it there.
    require_msg_auth = payload.require_message_authenticator
    if require_msg_auth is None:
        require_msg_auth = payload.nas_type == "vmware"

    client = RadiusClient(
        name=payload.name,
        ipaddr=payload.ipaddr,
        shared_secret_encrypted=encrypt_secret(payload.shared_secret),
        nas_type=payload.nas_type,
        description=payload.description,
        location=payload.location,
        tags=payload.tags,
        enabled=payload.enabled,
        require_message_authenticator=require_msg_auth,
        group_id=payload.group_id,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    audit.record(
        db, username=user.username, action="CREATE_RADIUS_CLIENT",
        object_ref=client.name, source_ip=_client_ip(request),
    )
    return _to_out(client)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db), _: User = Depends(require_any)):
    client = db.get(RadiusClient, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Client not found")
    return _to_out(client)


@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    client = db.get(RadiusClient, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Client not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != client.name:
        if db.scalar(select(RadiusClient).where(RadiusClient.name == data["name"])):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A client with this name exists")
    if data.get("group_id") is not None and not db.get(ClientGroup, data["group_id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="group_id does not exist")

    secret = data.pop("shared_secret", None)
    if secret is not None:
        client.shared_secret_encrypted = encrypt_secret(secret)
    for field, value in data.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    audit.record(
        db, username=user.username, action="UPDATE_RADIUS_CLIENT",
        object_ref=client.name, source_ip=_client_ip(request),
        detail="secret rotated" if secret is not None else None,
    )
    return _to_out(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    client = db.get(RadiusClient, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Client not found")
    name = client.name
    db.delete(client)
    db.commit()
    audit.record(
        db, username=user.username, action="DELETE_RADIUS_CLIENT",
        object_ref=name, source_ip=_client_ip(request),
    )


# --------------------------------------------------------------------------- #
# Client groups
# --------------------------------------------------------------------------- #
group_router = APIRouter(prefix="/client-groups", tags=["clients"])


def _group_out(g: ClientGroup, count: int) -> ClientGroupOut:
    return ClientGroupOut(id=g.id, name=g.name, description=g.description, client_count=count)


@group_router.get("", response_model=list[ClientGroupOut])
def list_groups(db: Session = Depends(get_db), _: User = Depends(require_any)):
    rows = db.execute(
        select(ClientGroup, func.count(RadiusClient.id))
        .outerjoin(RadiusClient, RadiusClient.group_id == ClientGroup.id)
        .group_by(ClientGroup.id)
        .order_by(ClientGroup.name)
    ).all()
    return [_group_out(g, count) for g, count in rows]


@group_router.post("", response_model=ClientGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: ClientGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if db.scalar(select(ClientGroup).where(ClientGroup.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A group with this name exists")
    group = ClientGroup(name=payload.name, description=payload.description)
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record(
        db, username=user.username, action="CREATE_CLIENT_GROUP",
        object_ref=group.name, source_ip=_client_ip(request),
    )
    return _group_out(group, 0)


@group_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    group = db.get(ClientGroup, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")
    name = group.name
    db.delete(group)
    db.commit()
    audit.record(
        db, username=user.username, action="DELETE_CLIENT_GROUP",
        object_ref=name, source_ip=_client_ip(request),
    )

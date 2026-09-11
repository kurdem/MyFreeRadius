"""Local user administration (issue #7). Administrator role only.

Guards against locking everyone out: the last active administrator cannot be
deleted, deactivated, or demoted.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas.auth import UserOut
from app.schemas.user_admin import UserCreate, UserUpdate
from app.security.deps import require_admin
from app.security.passwords import hash_password
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _active_admin_count(db: Session, *, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(
        User.role == UserRole.ADMINISTRATOR, User.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) or 0


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A user with this name exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(db, username=admin.username, action="CREATE_USER",
                 object_ref=user.username, source_ip=_client_ip(request))
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    # Would this change remove the last active administrator?
    demoting = "role" in data and data["role"] != UserRole.ADMINISTRATOR
    deactivating = data.get("is_active") is False
    if (demoting or deactivating) and user.role == UserRole.ADMINISTRATOR and user.is_active:
        if _active_admin_count(db, exclude_id=user.id) == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last active administrator",
            )

    if "role" in data:
        user.role = data["role"]
    if "is_active" in data:
        user.is_active = data["is_active"]
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
        user.failed_logins = 0
        user.locked_until = None
    db.commit()
    db.refresh(user)
    audit.record(db, username=admin.username, action="UPDATE_USER",
                 object_ref=user.username, source_ip=_client_ip(request),
                 detail="password reset" if data.get("password") else None)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    if user.role == UserRole.ADMINISTRATOR and user.is_active and _active_admin_count(
        db, exclude_id=user.id
    ) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Cannot delete the last active administrator")
    name = user.username
    db.delete(user)
    db.commit()
    audit.record(db, username=admin.username, action="DELETE_USER",
                 object_ref=name, source_ip=_client_ip(request))

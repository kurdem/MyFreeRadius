"""Authentication endpoints (spec section 21).

Includes login lockout: after a number of consecutive failures an account is
temporarily locked. Responses are deliberately generic to avoid user enumeration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, UserOut
from app.security.deps import get_current_user
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    cookie_kwargs,
    create_session_token,
)
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_FAILED = 5
_LOCK_MINUTES = 15
_GENERIC_ERROR = "Invalid username or password"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _is_locked(user: User) -> bool:
    if not user.locked_until:
        return False
    try:
        until = datetime.fromisoformat(user.locked_until)
    except ValueError:
        return False
    return until > datetime.now(timezone.utc)


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.username == payload.username))
    ip = _client_ip(request)

    # Uniform failure path (no user-enumeration difference in status/body).
    def _fail() -> None:
        audit.record(
            db, username=payload.username, action="LOGIN", source_ip=ip, result="FAILURE"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_ERROR)

    if user is None or not user.is_active:
        # Still spend time hashing to reduce timing side channel.
        verify_password(payload.password, hash_password("timing-equalizer"))
        _fail()

    if _is_locked(user):
        audit.record(
            db, username=user.username, action="LOGIN", source_ip=ip,
            result="FAILURE", detail="account locked",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked. Try again later.",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= _MAX_FAILED:
            user.locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=_LOCK_MINUTES)
            ).isoformat()
            user.failed_logins = 0
        db.commit()
        _fail()

    # Success: reset counters, opportunistically upgrade the hash.
    user.failed_logins = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    db.commit()

    token, csrf = create_session_token(user.id, user.username, user.role.value)
    response.set_cookie(SESSION_COOKIE, token, **cookie_kwargs())
    # CSRF cookie is readable by JS so the SPA can echo it in a header.
    csrf_kwargs = cookie_kwargs()
    csrf_kwargs["httponly"] = False
    response.set_cookie(CSRF_COOKIE, csrf, **csrf_kwargs)

    audit.record(db, username=user.username, action="LOGIN", source_ip=ip, result="SUCCESS")
    return user


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    audit.record(
        db, username=user.username, action="CHANGE_PASSWORD",
        source_ip=_client_ip(request), result="SUCCESS",
    )
    return {"message": "Password changed"}

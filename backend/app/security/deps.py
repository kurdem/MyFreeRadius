"""Authentication / authorization FastAPI dependencies (spec sections 21, 22)."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security.sessions import (
    CSRF_HEADER,
    SESSION_COOKIE,
    decode_session_token,
)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_session_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    # Double-submit CSRF check on state-changing requests.
    if request.method not in _SAFE_METHODS:
        header_token = request.headers.get(CSRF_HEADER)
        if not header_token or header_token != payload.get("csrf"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
            )

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing that the current user has one of ``roles``."""

    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges for this action",
            )
        return user

    return _dep


# Convenience dependencies.
require_admin = require_roles(UserRole.ADMINISTRATOR)
require_operator = require_roles(UserRole.ADMINISTRATOR, UserRole.OPERATOR)
require_any = require_roles(UserRole.ADMINISTRATOR, UserRole.OPERATOR, UserRole.AUDITOR)

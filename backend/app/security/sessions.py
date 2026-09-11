"""Signed session tokens (JWT) and CSRF tokens (spec section 21).

Design:

* The session is a short-lived JWT stored in an **httpOnly** cookie so it is not
  reachable from JavaScript (XSS mitigation).
* CSRF protection uses the double-submit-cookie pattern: a random token is set
  in a non-httpOnly cookie and must be echoed back in the ``X-CSRF-Token``
  header on state-changing requests. Both are bound to the session id.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings

SESSION_COOKIE = "radiusmgr_session"
CSRF_COOKIE = "radiusmgr_csrf"
CSRF_HEADER = "x-csrf-token"
_ALGO = "HS256"


def create_session_token(user_id: int, username: str, role: str) -> tuple[str, str]:
    """Return ``(jwt, csrf_token)``. The csrf token is embedded in the jwt too."""
    settings = get_settings()
    csrf = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "csrf": csrf,
        "iat": now,
        "exp": now + timedelta(minutes=settings.session_ttl_minutes),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=_ALGO)
    return token, csrf


def decode_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGO])


def cookie_kwargs() -> dict[str, Any]:
    """Cookie flags. ``Secure`` is disabled in dev so http://localhost works."""
    settings = get_settings()
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.is_production,
        "max_age": settings.session_ttl_minutes * 60,
        "path": "/",
    }

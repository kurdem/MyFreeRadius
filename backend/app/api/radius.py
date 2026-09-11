"""RADIUS-facing authorization endpoint (Phase 4).

Called by FreeRADIUS via rlm_rest when MFA is enabled. Authenticated by a shared
token in the request body (machine-to-machine on the internal network), NOT by a
session cookie - so this router deliberately does not use the session/CSRF deps.

Returns HTTP 200 to accept and 401 to reject, which rlm_rest maps to
Access-Accept / Access-Reject. Passwords and OTPs are never logged.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.mfa import RadiusAuthRequest
from app.services import audit, radius_auth

router = APIRouter(prefix="/radius", tags=["radius"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/authorize")
def authorize(
    payload: RadiusAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    expected = get_settings().radius_agent_token
    if not expected or not secrets.compare_digest(payload.token, expected):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"result": "reject", "reason": "unauthorized"}

    accept, reason = radius_auth.authorize(db, payload.username, payload.password)
    audit.record(
        db, username=payload.username, action="RADIUS_AUTHORIZE",
        source_ip=_client_ip(request),
        result="SUCCESS" if accept else "FAILURE", detail=reason,
    )
    if not accept:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"result": "reject", "reason": reason}
    return {"result": "accept"}

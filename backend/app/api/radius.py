"""RADIUS-facing authorization endpoint (Phase 4).

Called by FreeRADIUS via rlm_rest when MFA is enabled. Authenticated by a shared
token (body ``token`` field or ``X-Agent-Token`` / ``Authorization: Bearer``
header) - machine-to-machine on the internal network, NOT a session cookie, so
this router deliberately does not use the session/CSRF deps.

The request body is parsed tolerantly: it accepts our flat
``{"username","password","token"}`` JSON, the native rlm_rest attribute JSON
(``{"User-Name":{"value":[".."]}}`` and variants), and form-encoded bodies. This
avoids brittle coupling to one rlm_rest body format.

Returns HTTP 200 to accept and 401 to reject (mapped by rlm_rest to
Access-Accept / Access-Reject). Passwords and OTPs are never logged.
"""
from __future__ import annotations

import json
import logging
import secrets
import urllib.parse

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services import audit, radius_auth

router = APIRouter(prefix="/radius", tags=["radius"])
logger = logging.getLogger("radius_auth")


def _rlm_value(v):
    """Pull a scalar out of the various rlm_rest attribute encodings."""
    if isinstance(v, dict):
        val = v.get("value", v.get("values"))
        v = val
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _parse_body(raw: bytes, content_type: str) -> dict:
    text = raw.decode("utf-8", "replace").strip()
    result = {"username": None, "password": None, "token": None}
    if not text:
        return result
    if "json" in content_type or text.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError:
            return result
        if not isinstance(obj, dict):
            return result
        result["username"] = obj.get("username")
        result["password"] = obj.get("password")
        result["token"] = obj.get("token")
        # rlm_rest native attribute names (case-insensitive-ish lookups).
        for key in ("User-Name", "user-name", "Stripped-User-Name"):
            if result["username"] is None and key in obj:
                result["username"] = _rlm_value(obj[key])
        for key in ("User-Password", "user-password", "Cleartext-Password"):
            if result["password"] is None and key in obj:
                result["password"] = _rlm_value(obj[key])
        return result
    # Form-encoded fallback.
    parsed = urllib.parse.parse_qs(text)

    def _f(*keys):
        for k in keys:
            if k in parsed and parsed[k]:
                return parsed[k][0]
        return None

    result["username"] = _f("username", "User-Name")
    result["password"] = _f("password", "User-Password")
    result["token"] = _f("token")
    return result


def _token_from_headers(request: Request) -> str | None:
    hdr = request.headers.get("x-agent-token")
    if hdr:
        return hdr
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


@router.post("/authorize")
async def authorize(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    data = _parse_body(raw, content_type)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    # Token may arrive in the body, a header, or the query string - whichever the
    # rlm_rest body format allows.
    token = (
        data.get("token")
        or _token_from_headers(request)
        or request.query_params.get("token")
    )

    # Always log the arrival (never secrets) so failures are diagnosable.
    logger.info(
        "radius_authorize_recv",
        extra={"event": "radius_authorize_recv", "user": username or "?",
               "result": f"content_type={content_type or 'none'} "
                         f"has_password={bool(password)} has_token={bool(token)}"},
    )

    expected = get_settings().radius_agent_token
    if not expected or not token or not secrets.compare_digest(token, expected):
        logger.warning("radius_authorize_unauthorized",
                       extra={"event": "radius_authorize", "user": username or "?",
                              "result": "bad or missing agent token"})
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"result": "reject", "reason": "unauthorized"}

    if not username:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"result": "reject", "reason": "missing username"}

    accept, reason = radius_auth.authorize(db, username, password)
    audit.record(
        db, username=username, action="RADIUS_AUTHORIZE",
        source_ip=request.client.host if request.client else None,
        result="SUCCESS" if accept else "FAILURE", detail=reason,
    )
    if not accept:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"result": "reject", "reason": reason}
    return {"result": "accept"}

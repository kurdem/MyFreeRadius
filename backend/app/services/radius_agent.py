"""Client for the FreeRADIUS control agent (spec sections 3, 12, 13, 14, 15).

The backend never runs ``freeradius`` itself. Instead it talks to a small agent
that runs *inside* the FreeRADIUS container over the internal Docker network,
authenticated with a shared bearer token. This keeps privilege where it belongs
and avoids mounting the Docker socket into the backend.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("radius_agent")


class AgentError(RuntimeError):
    """Raised when the control agent is unreachable or returns an error."""


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().radius_agent_token}"}


def _base_url() -> str:
    return get_settings().radius_agent_url.rstrip("/")


def _post(path: str, json: dict, timeout: float = 30.0) -> dict:
    try:
        resp = httpx.post(f"{_base_url()}{path}", json=json, headers=_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise AgentError(f"FreeRADIUS control agent unreachable: {exc}") from exc
    if resp.status_code >= 500:
        raise AgentError(f"Control agent error {resp.status_code}: {resp.text[:500]}")
    if resp.status_code == 401:
        raise AgentError("Control agent rejected the agent token (401)")
    return resp.json()


def _get(path: str, params: dict | None = None, timeout: float = 15.0) -> dict:
    try:
        resp = httpx.get(f"{_base_url()}{path}", params=params, headers=_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise AgentError(f"FreeRADIUS control agent unreachable: {exc}") from exc
    if resp.status_code >= 500:
        raise AgentError(f"Control agent error {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def validate_config(files: dict, deletes: list | None = None) -> dict:
    """Validate a candidate config bundle via ``freeradius -XC``.

    ``files`` maps managed relative paths to content; ``deletes`` lists managed
    paths to remove. Returns ``{"valid": bool, "message": str, "details": str}``.
    """
    return _post("/config/validate", {"files": files, "deletes": deletes or []})


def apply_config(files: dict, deletes: list | None = None) -> dict:
    """Validate, back up, write the bundle, and reload FreeRADIUS.

    Returns ``{"success": bool, "message": str, "details": str}``. The agent
    rolls the whole bundle back if the reload fails.
    """
    return _post("/config/apply", {"files": files, "deletes": deletes or []}, timeout=60.0)


def status() -> dict:
    """Return FreeRADIUS process/health status."""
    return _get("/status")


def logs(limit: int = 200) -> dict:
    """Return the last ``limit`` lines of the RADIUS log (already masked)."""
    return _get("/logs", params={"limit": limit})

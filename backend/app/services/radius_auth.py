"""RADIUS authorization with TOTP MFA (Phase 4).

Called by FreeRADIUS (rlm_rest) when MFA is enabled. Implements two modes:

* ``totp_only``             - validate the OTP only (Horizon validated the AD
  password itself). Optionally enforce AD group membership.
* ``ad_password_plus_totp`` - User-Password = "<ad-password><6-digit OTP>"; we
  split it, verify the OTP, then bind to AD to verify the password.

Never logs passwords or OTPs.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ADConfig, ADGroup, GroupAccess, UserTotp
from app.services import cert_service, ldap_service, totp_service

logger = logging.getLogger("radius_auth")


def _token(db: Session, username: str) -> UserTotp | None:
    return db.scalar(
        select(UserTotp).where(
            func.lower(UserTotp.username) == username.lower(),
            UserTotp.confirmed.is_(True),
        )
    )


def _group_ok(db: Session, user_group_dns: list[str]) -> bool:
    """Apply allow/deny AD group policy (case-insensitive DN match)."""
    have = {g.lower() for g in user_group_dns}
    groups = db.scalars(select(ADGroup)).all()
    deny = {g.group_dn.lower() for g in groups if g.access == GroupAccess.DENY}
    allow = {g.group_dn.lower() for g in groups if g.access == GroupAccess.ALLOW}
    if have & deny:
        return False
    if allow and not (have & allow):
        return False
    return True


def authorize(db: Session, username: str, password: str) -> tuple[bool, str]:
    """Return ``(accept, reason)``. ``reason`` is safe to log (no secrets)."""
    cfg = db.get(ADConfig, 1)
    if cfg is None or not cfg.mfa_enabled:
        return False, "MFA is not enabled"

    token = _token(db, username)
    if token is None:
        return False, "no confirmed MFA token for user"

    if cfg.mfa_mode == "ad_password_plus_totp":
        if len(password) < 7:
            return False, "password too short (expected AD password + 6-digit OTP)"
        ad_password, otp = password[:-6], password[-6:]
    else:  # totp_only
        ad_password, otp = None, password

    if not totp_service.verify(token.secret_encrypted, otp):
        return False, "invalid OTP"

    # Group membership + (for append mode) AD password check.
    if cfg.enabled:
        ca_bundle = cert_service.build_bundle(db)
        user_dn, groups = ldap_service.find_user(cfg, username, ca_bundle=ca_bundle)
        if user_dn is None:
            return False, "user not found in AD"
        if not _group_ok(db, groups):
            return False, "user not in an allowed AD group"
        if ad_password is not None and not ldap_service.check_password(
            cfg, user_dn, ad_password, ca_bundle=ca_bundle
        ):
            return False, "invalid AD password"

    return True, "ok"

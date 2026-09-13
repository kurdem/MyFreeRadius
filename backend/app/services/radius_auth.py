"""RADIUS authorization: TOTP MFA (Phase 4) + policy engine (Phase 7).

Called by FreeRADIUS (rlm_rest) when the generated ``manager`` site delegates to
the backend, which happens when MFA is enabled OR authentication policies are in
use. Implements:

* MFA modes (when enabled):
  * ``totp_only``             - validate the OTP only (Horizon validated the AD
    password itself). Optionally enforce AD group membership.
  * ``ad_password_plus_totp`` - User-Password = "<ad-password><6-digit OTP>"; we
    split it, verify the OTP, then bind to AD to verify the password.
* Authentication policies (always, when any enabled policy exists): first-match
  rules over (client group, AD group) -> allow/deny + reply attributes.

Returns ``(accept, reason, reply_attributes)``. Never logs passwords or OTPs.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ADConfig, ADGroup, GroupAccess, UserTotp
from app.services import cert_service, ldap_service, policy_service, totp_service

logger = logging.getLogger("radius_auth")


def _token(db: Session, username: str) -> UserTotp | None:
    return db.scalar(
        select(UserTotp).where(
            func.lower(UserTotp.username) == username.lower(),
            UserTotp.confirmed.is_(True),
        )
    )


def _group_ok(db: Session, user_group_dns: list[str]) -> bool:
    """Apply the coarse allow/deny AD group list (case-insensitive DN match)."""
    have = {g.lower() for g in user_group_dns}
    groups = db.scalars(select(ADGroup)).all()
    deny = {g.group_dn.lower() for g in groups if g.access == GroupAccess.DENY}
    allow = {g.group_dn.lower() for g in groups if g.access == GroupAccess.ALLOW}
    if have & deny:
        return False
    if allow and not (have & allow):
        return False
    return True


def authorize(
    db: Session,
    username: str,
    password: str,
    *,
    client_group_id: int | None = None,
) -> tuple[bool, str, list[dict]]:
    """Return ``(accept, reason, reply_attributes)``. ``reason`` has no secrets."""
    cfg = db.get(ADConfig, 1)
    mfa_on = cfg is not None and cfg.mfa_enabled

    # --- OTP handling -------------------------------------------------------- #
    if mfa_on:
        token = _token(db, username)
        if token is None:
            return False, "no confirmed MFA token for user", []
        if cfg.mfa_mode == "ad_password_plus_totp":
            if len(password) < 7:
                return False, "password too short (expected AD password + 6-digit OTP)", []
            ad_password, otp = password[:-6], password[-6:]
        else:  # totp_only
            ad_password, otp = None, password
        if not totp_service.verify(token.secret_encrypted, otp):
            return False, "invalid OTP", []
    else:
        # Policy-only mode: the password (if any) is the AD password. Horizon may
        # have validated it upstream (then it arrives empty).
        ad_password, otp = (password or None), None

    # --- AD lookup + coarse group gate + optional password bind -------------- #
    user_group_dns: list[str] = []
    if cfg is not None and cfg.enabled:
        ca_bundle = cert_service.build_bundle(db)
        user_dn, user_group_dns = ldap_service.find_user(cfg, username, ca_bundle=ca_bundle)
        if user_dn is None:
            return False, "user not found in AD", []
        if not _group_ok(db, user_group_dns):
            return False, "user not in an allowed AD group", []
        if ad_password is not None and not ldap_service.check_password(
            cfg, user_dn, ad_password, ca_bundle=ca_bundle
        ):
            return False, "invalid AD password", []

    # --- Policy engine (client group + AD group -> allow/deny + reply) ------- #
    decision = policy_service.evaluate(
        db, client_group_id=client_group_id, user_group_dns=user_group_dns
    )
    if decision.had_policies and not decision.allow:
        return False, decision.reason, []

    # Refuse if nothing actually authenticated the user.
    verified = mfa_on or (ad_password is not None and cfg is not None and cfg.enabled)
    policy_allowed = decision.had_policies and decision.allow
    if not verified and not policy_allowed:
        return False, "no authentication method configured", []

    return True, "ok", decision.reply_attributes

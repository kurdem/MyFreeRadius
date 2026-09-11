"""Generate FreeRADIUS ``clients.conf`` from the database (spec section 3).

Flow:  Database -> Configuration Generator -> clients.conf -> validate -> reload.

The generator is deterministic (clients sorted by name) so the same data always
produces byte-identical output, which makes checksums and diffs meaningful.
Secrets were validated on input (no quotes/backslashes/whitespace), so wrapping
them in double quotes here is injection-safe.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ADConfig, ADGroup, GroupAccess, RadiusClient
from app.security.crypto import decrypt_secret

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=(), default=False),
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)

# FreeRADIUS config uses %{...} and {% ... %} style expansions that collide with
# Jinja's default delimiters, so the FR module/site templates use custom ones.
_fr_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
    variable_start_string="[[",
    variable_end_string="]]",
    block_start_string="[%",
    block_end_string="%]",
    comment_start_string="[#",
    comment_end_string="#]",
)


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def generate_clients_conf(db: Session, *, version: int, virtual_server: str | None = None) -> str:
    """Render clients.conf for all *enabled* clients, ordered by name.

    When ``virtual_server`` is set, each client is routed to that FreeRADIUS
    virtual server (used to send requests to the generated "manager" server).
    """
    clients = db.scalars(
        select(RadiusClient).where(RadiusClient.enabled.is_(True)).order_by(RadiusClient.name)
    ).all()
    rendered_clients = [
        {
            "name": c.name,
            "ipaddr": c.ipaddr,
            "secret": decrypt_secret(c.shared_secret_encrypted),
            "nas_type": c.nas_type,
            "description": c.description,
            "require_message_authenticator": c.require_message_authenticator,
        }
        for c in clients
    ]
    template = _env.get_template("clients.conf.j2")
    return template.render(
        clients=rendered_clients,
        version=version,
        virtual_server=virtual_server,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def generate_ldap_module(ad: ADConfig) -> str:
    """Render mods-enabled/ldap from the AD configuration."""
    hosts = [h for h in (ad.primary_dc, ad.secondary_dc) if h]
    if ad.use_ldaps:
        server_uri = " ".join(f"ldaps://{h}" for h in hosts)
        require_cert = "demand" if ad.verify_tls else "never"
    else:
        server_uri = " ".join(hosts)
        require_cert = "never"
    return _fr_env.get_template("ldap.conf.j2").render(
        generated_at=_now(),
        server_uri=server_uri,
        port=ad.port,
        bind_user=ad.bind_user,
        bind_password=decrypt_secret(ad.bind_password_encrypted),
        base_dn=ad.base_dn,
        timeout=ad.timeout_seconds,
        require_cert=require_cert,
    )


def generate_manager_site(groups: list[ADGroup]) -> str:
    """Render sites-enabled/manager (LDAP mode) with AD group authorization."""
    allow_groups = [g.group_dn for g in groups if g.access == GroupAccess.ALLOW]
    deny_groups = [g.group_dn for g in groups if g.access == GroupAccess.DENY]
    return _fr_env.get_template("manager_site.conf.j2").render(
        generated_at=_now(),
        allow_groups=allow_groups,
        deny_groups=deny_groups,
    )


def generate_rest_module(backend_url: str) -> str:
    """Render mods-enabled/rest pointing at the manager backend."""
    return _fr_env.get_template("rest.conf.j2").render(
        generated_at=_now(),
        backend_url=backend_url.rstrip("/"),
    )


def generate_manager_site_rest() -> str:
    """Render sites-enabled/manager (MFA mode) that delegates to rlm_rest."""
    return _fr_env.get_template("manager_site_rest.conf.j2").render(generated_at=_now())


# Managed FreeRADIUS files that may be present depending on mode. Any not written
# in the current state is listed for deletion so mode switches are clean. We
# never delete the stock "default" site (clients route to "manager" instead).
_MANAGED_FR_FILES = {"mods-enabled/ldap", "mods-enabled/rest", "sites-enabled/manager"}


def generate_bundle(db: Session, *, version: int, backend_url: str = "http://backend:8000") -> dict:
    """Build the full config bundle from the database.

    Returns ``{"files": {relpath: content}, "deletes": [relpath]}``.

    States:
      * AD disabled          -> only ``clients.conf`` (stock "default" handles them).
      * AD enabled, MFA off   -> ``clients.conf`` (routed to "manager") + ldap
                                 module + "manager" site (PAP-bind + group authz).
      * AD enabled, MFA on    -> ``clients.conf`` (routed) + rest module + "manager"
                                 site delegating to the backend (TOTP + AD).
    """
    ad = db.get(ADConfig, 1)
    ad_enabled = ad is not None and ad.enabled
    mfa_enabled = ad is not None and ad.enabled and ad.mfa_enabled

    virtual_server = "manager" if ad_enabled else None
    files: dict[str, str] = {
        "clients.conf": generate_clients_conf(db, version=version, virtual_server=virtual_server),
    }

    if mfa_enabled:
        files["mods-enabled/rest"] = generate_rest_module(backend_url)
        files["sites-enabled/manager"] = generate_manager_site_rest()
    elif ad_enabled:
        groups = db.scalars(select(ADGroup).order_by(ADGroup.name)).all()
        files["mods-enabled/ldap"] = generate_ldap_module(ad)
        files["sites-enabled/manager"] = generate_manager_site(list(groups))

    # Anything managed but not written in this state should be removed.
    deletes = sorted(_MANAGED_FR_FILES - set(files.keys()))
    return {"files": files, "deletes": deletes}


def bundle_checksum(bundle: dict) -> str:
    return checksum(json.dumps(bundle, sort_keys=True))

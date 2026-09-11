"""Generate FreeRADIUS ``clients.conf`` from the database (spec section 3).

Flow:  Database -> Configuration Generator -> clients.conf -> validate -> reload.

The generator is deterministic (clients sorted by name) so the same data always
produces byte-identical output, which makes checksums and diffs meaningful.
Secrets were validated on input (no quotes/backslashes/whitespace), so wrapping
them in double quotes here is injection-safe.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RadiusClient
from app.security.crypto import decrypt_secret

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=(), default=False),
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def generate_clients_conf(db: Session, *, version: int) -> str:
    """Render clients.conf for all *enabled* clients, ordered by name."""
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
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

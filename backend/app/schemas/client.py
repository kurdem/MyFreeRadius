"""RADIUS client schemas with strict validation.

Validation here is a security boundary: values flow into the generated
FreeRADIUS ``clients.conf``. We reject anything that could break out of a
config token or inject directives (spec section 26 - Command/Config Injection).
"""
from __future__ import annotations

import ipaddress
import re

from pydantic import BaseModel, Field, field_validator

# A FreeRADIUS client short-name / identifier: letters, digits, dash, underscore, dot.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
# Shared secret: printable ASCII without quotes, backslashes, or whitespace that
# would break the quoted config token. Keeps secrets robust and injection-safe.
_SECRET_RE = re.compile(r'^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}:;,.?~]{8,128}$')
_ALLOWED_NAS_TYPES = {"other", "omnissa", "cisco", "juniper", "mikrotik", "aruba"}
# Backward-compatible aliases normalised to the canonical value. "vmware" was the
# old name before VMware Horizon became Omnissa Horizon.
_NAS_ALIASES = {"vmware": "omnissa"}


def _normalise_nas(value: str) -> str:
    value = _NAS_ALIASES.get(value, value)
    if value not in _ALLOWED_NAS_TYPES:
        raise ValueError(f"nas_type must be one of: {', '.join(sorted(_ALLOWED_NAS_TYPES))}")
    return value


def _validate_ip_or_cidr(value: str) -> str:
    value = value.strip()
    try:
        # Accept single host or network in CIDR notation.
        if "/" in value:
            ipaddress.ip_network(value, strict=False)
        else:
            ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("ipaddr must be a valid IPv4/IPv6 address or CIDR network") from exc
    return value


class ClientBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ipaddr: str = Field(min_length=1, max_length=64)
    nas_type: str = Field(default="other", max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=120)
    tags: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    # None on create -> resolved by NAS type (on for omnissa). Explicit value wins.
    require_message_authenticator: bool | None = None
    group_id: int | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name may only contain letters, digits, dot, dash and underscore"
            )
        return v

    @field_validator("ipaddr")
    @classmethod
    def _valid_ip(cls, v: str) -> str:
        return _validate_ip_or_cidr(v)

    @field_validator("nas_type")
    @classmethod
    def _valid_nas(cls, v: str) -> str:
        return _normalise_nas(v)


class ClientCreate(ClientBase):
    shared_secret: str = Field(min_length=8, max_length=128)

    @field_validator("shared_secret")
    @classmethod
    def _valid_secret(cls, v: str) -> str:
        if not _SECRET_RE.match(v):
            raise ValueError(
                "shared_secret contains invalid characters or is too short "
                "(8-128 chars, no quotes/backslashes/whitespace)"
            )
        return v


class ClientUpdate(BaseModel):
    """All fields optional; secret only rotated when provided."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    ipaddr: str | None = Field(default=None, min_length=1, max_length=64)
    nas_type: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=120)
    tags: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    require_message_authenticator: bool | None = None
    group_id: int | None = None
    shared_secret: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _NAME_RE.match(v):
            raise ValueError(
                "name may only contain letters, digits, dot, dash and underscore"
            )
        return v

    @field_validator("ipaddr")
    @classmethod
    def _valid_ip(cls, v: str | None) -> str | None:
        return None if v is None else _validate_ip_or_cidr(v)

    @field_validator("nas_type")
    @classmethod
    def _valid_nas(cls, v: str | None) -> str | None:
        return None if v is None else _normalise_nas(v)

    @field_validator("shared_secret")
    @classmethod
    def _valid_secret(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _SECRET_RE.match(v):
            raise ValueError(
                "shared_secret contains invalid characters or is too short "
                "(8-128 chars, no quotes/backslashes/whitespace)"
            )
        return v


class ClientOut(ClientBase):
    id: int
    # The plaintext secret is never returned; only whether one is set.
    has_secret: bool = True

    model_config = {"from_attributes": True}


class ClientGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name may only contain letters, digits, dot, dash and underscore"
            )
        return v


class ClientGroupCreate(ClientGroupBase):
    pass


class ClientGroupOut(ClientGroupBase):
    id: int
    client_count: int = 0

    model_config = {"from_attributes": True}

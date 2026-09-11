"""Active Directory schemas with validation (spec sections 6, 7, 26).

Values here will later feed a generated FreeRADIUS ``ldap`` module, so we keep
them free of control characters and within sane bounds now.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from app.models import GroupAccess

# Hostnames / FQDNs / IPs: letters, digits, dot, dash (no spaces/control chars).
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,255}$")
# A conservative charset for DNs and domains: no control chars, quotes or backslashes.
_DN_RE = re.compile(r"^[A-Za-z0-9 .,_=\-*/@()]{1,512}$")


def _valid_host(v: str) -> str:
    v = v.strip()
    if not _HOST_RE.match(v):
        raise ValueError("must be a valid hostname/FQDN/IP (letters, digits, dot, dash)")
    return v


def _valid_dnish(v: str, field: str) -> str:
    v = v.strip()
    if not _DN_RE.match(v):
        raise ValueError(f"{field} contains invalid characters")
    return v


class ADConfigBase(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    primary_dc: str = Field(min_length=1, max_length=255)
    secondary_dc: str | None = Field(default=None, max_length=255)
    port: int = Field(default=389, ge=1, le=65535)
    use_ldaps: bool = False
    verify_tls: bool = True
    base_dn: str = Field(min_length=1, max_length=512)
    bind_user: str = Field(min_length=1, max_length=255)
    timeout_seconds: int = Field(default=5, ge=1, le=120)
    enabled: bool = False

    @field_validator("domain")
    @classmethod
    def _valid_domain(cls, v: str) -> str:
        return _valid_host(v)

    @field_validator("primary_dc")
    @classmethod
    def _valid_primary(cls, v: str) -> str:
        return _valid_host(v)

    @field_validator("secondary_dc")
    @classmethod
    def _valid_secondary(cls, v: str | None) -> str | None:
        return None if v in (None, "") else _valid_host(v)

    @field_validator("base_dn")
    @classmethod
    def _valid_base(cls, v: str) -> str:
        return _valid_dnish(v, "base_dn")

    @field_validator("bind_user")
    @classmethod
    def _valid_bind(cls, v: str) -> str:
        # Accept UPN (svc-radius@corp.example.local) or a DN.
        return _valid_dnish(v, "bind_user")


class ADConfigUpsert(ADConfigBase):
    # Password optional on update to keep the stored one; required effectively on
    # first save (enforced in the endpoint if none is stored yet).
    bind_password: str | None = Field(default=None, max_length=256)


class ADConfigOut(ADConfigBase):
    configured: bool = True
    has_bind_password: bool = True

    model_config = {"from_attributes": True}


class ADConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: str | None = None


class ADGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    group_dn: str = Field(min_length=1, max_length=512)
    access: GroupAccess = GroupAccess.ALLOW
    attribute: str | None = Field(default=None, max_length=120)

    @field_validator("group_dn")
    @classmethod
    def _valid_group_dn(cls, v: str) -> str:
        return _valid_dnish(v, "group_dn")

    @field_validator("attribute")
    @classmethod
    def _valid_attr(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not re.match(r"^[A-Za-z0-9 ._\-]{1,120}$", v):
            raise ValueError("attribute contains invalid characters")
        return v


class ADGroupCreate(ADGroupBase):
    pass


class ADGroupOut(ADGroupBase):
    id: int

    model_config = {"from_attributes": True}

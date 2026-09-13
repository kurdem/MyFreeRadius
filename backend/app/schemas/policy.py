"""Authentication policy schemas (Phase 7)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import PolicyAction


class ReplyAttribute(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=253)


class PolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=100000)
    enabled: bool = True
    client_group_id: int | None = None
    ad_group_dn: str | None = Field(default=None, max_length=512)
    ad_group_name: str | None = Field(default=None, max_length=120)
    action: PolicyAction = PolicyAction.ALLOW
    reply_attributes: list[ReplyAttribute] = Field(default_factory=list)


class PolicyCreate(PolicyBase):
    pass


class PolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    priority: int | None = Field(default=None, ge=0, le=100000)
    enabled: bool | None = None
    client_group_id: int | None = None
    ad_group_dn: str | None = Field(default=None, max_length=512)
    ad_group_name: str | None = Field(default=None, max_length=120)
    action: PolicyAction | None = None
    reply_attributes: list[ReplyAttribute] | None = None


class PolicyOut(PolicyBase):
    id: int
    client_group_name: str | None = None

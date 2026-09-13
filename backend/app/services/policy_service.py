"""Authentication policy engine (Phase 7).

Ordered, first-match evaluation of :class:`AuthPolicy` rules. Used by the backend
authorize path to decide allow/deny and to collect RADIUS reply attributes.

Semantics:
  * No enabled policies at all -> ``had_policies=False``; the caller keeps its
    existing behaviour (backwards compatible; policies are opt-in).
  * Policies exist but none match -> default DENY (secure default).
  * First matching enabled rule (ascending priority, then id) decides.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthPolicy, PolicyAction


@dataclass
class PolicyDecision:
    had_policies: bool
    allow: bool
    reason: str
    reply_attributes: list[dict] = field(default_factory=list)
    policy_name: str | None = None


def _parse_reply(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and item.get("name"):
            out.append({"name": str(item["name"]), "value": str(item.get("value", ""))})
    return out


def _matches(policy: AuthPolicy, client_group_id: int | None, user_group_dns_lower: set[str]) -> bool:
    if policy.client_group_id is not None and policy.client_group_id != client_group_id:
        return False
    if policy.ad_group_dn is not None and policy.ad_group_dn.lower() not in user_group_dns_lower:
        return False
    return True


def evaluate(
    db: Session,
    *,
    client_group_id: int | None,
    user_group_dns: list[str],
) -> PolicyDecision:
    policies = db.scalars(
        select(AuthPolicy)
        .where(AuthPolicy.enabled.is_(True))
        .order_by(AuthPolicy.priority.asc(), AuthPolicy.id.asc())
    ).all()
    if not policies:
        return PolicyDecision(had_policies=False, allow=True, reason="no policies defined")

    have = {g.lower() for g in user_group_dns}
    for policy in policies:
        if _matches(policy, client_group_id, have):
            if policy.action == PolicyAction.ALLOW:
                return PolicyDecision(
                    had_policies=True,
                    allow=True,
                    reason=f"allowed by policy '{policy.name}'",
                    reply_attributes=_parse_reply(policy.reply_attributes),
                    policy_name=policy.name,
                )
            return PolicyDecision(
                had_policies=True,
                allow=False,
                reason=f"denied by policy '{policy.name}'",
                policy_name=policy.name,
            )

    return PolicyDecision(had_policies=True, allow=False, reason="no matching policy (default deny)")

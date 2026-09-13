# Authentication Policies (Phase 7)

Authentication policies are an ordered, **first-match** rule set that maps a
request's **RADIUS client group** and the user's **AD group membership** to an
**allow / deny** decision, plus optional RADIUS **reply attributes**. They are
enforced in the backend, so they apply with or without MFA.

## How it works

- Each rule has a **priority** (lower is evaluated first), an optional **client
  group** and **AD group DN**, an **action** (allow/deny), and optional **reply
  attributes** returned on allow.
- A rule matches when its conditions hold: an empty client group or AD group
  means *any*. The **first** matching, enabled rule decides.
- **No policies defined** → authentication is unaffected (policies are opt-in).
- **Policies exist but none match** → the request is **denied** (secure default).

## Enforcement

When any enabled policy exists (and AD is enabled), the generated FreeRADIUS
`manager` virtual server delegates the decision to the backend via `rlm_rest` —
the same path used by MFA. The `rest` module additionally sends the client
identity (`Client-Shortname`, `Packet-Src-IP-Address`) so the backend can map
the request to a client group.

```
Horizon → RADIUS client → FreeRADIUS (manager) → rlm_rest → backend
   backend: MFA (if enabled) → AD lookup + group gate → POLICY ENGINE → accept/deny (+ reply attrs)
```

If neither MFA nor any policy is active, authentication keeps using the direct
LDAP path (no backend in the hot path), exactly as before.

## Reply attributes

On an allow, a policy can attach RADIUS reply attributes (for example
`Filter-Id`, `Class`, or a vendor attribute). The backend returns them to
`rlm_rest`, which applies them to the RADIUS reply. Use attribute names exactly
as FreeRADIUS knows them.

## Managing policies

**Policies** page in the UI (administrators):

1. **New policy** — set name, priority, optional client group, optional AD group
   DN, action, and any reply attributes.
2. Reorder by editing the **priority** (lower runs first).
3. Toggle **Enabled** to stage a rule without deleting it.

All changes are audited (`CREATE_POLICY` / `UPDATE_POLICY` / `DELETE_POLICY`).

## Example

> Deny the `Contractors` AD group on the `External-Horizon` client group, allow
> everyone else and tag staff with a filter.

| Priority | Client group      | AD group DN                | Action | Reply |
|---------:|-------------------|----------------------------|--------|-------|
| 10       | External-Horizon  | CN=Contractors,DC=corp,... | deny   | —     |
| 20       | *(any)*           | CN=Staff,DC=corp,...       | allow  | `Filter-Id = staff-acl` |
| 30       | *(any)*           | *(any)*                    | allow  | —     |

A contractor from the external cluster is denied by rule 10; staff get the
filter from rule 20; everyone else is allowed by the catch-all rule 30.

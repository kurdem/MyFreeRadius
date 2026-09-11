# Active Directory integration (Phase 3 — roadmap)

> **Not yet implemented.** This page documents the planned design so the intent
> is clear. In the UI, Active Directory, Certificates and Policies are shown as
> **Coming Soon** and perform no actions.

## Planned scope

- Configure the AD connection: domain, one or more domain controllers,
  LDAP (389) / LDAPS (636), Base DN, bind user + bind password, timeouts.
- LDAPS with CA certificate validation (certificate management page).
- Restrict RADIUS authentication to specific AD groups (allow-lists).
- Map AD groups → policies → allow/deny + reply attributes (Phase 4).

## Planned data handling

- Bind passwords stored **encrypted at rest** (Fernet), like shared secrets —
  never returned in plaintext, never logged, never exported by default.
- CA certificates managed with expiry warnings (30 / 7 / expired).

## Planned FreeRADIUS mapping

The generator will render an `ldap` module instance and wire it into the
authorize/authenticate sections, with group checks expressed as policy rules.
The exact authentication method offered to Horizon (PAP vs MS-CHAPv2) will be
constrained by the chosen AD backend — see [horizon.md](horizon.md).

## Why it is staged

Doing AD safely requires the certificate store, secret handling for bind
credentials, and a policy engine. These are built in Phases 3–4 rather than
shipped as a non-functional form. Everything shown in the UI today performs a
real action or is explicitly labelled Coming Soon.

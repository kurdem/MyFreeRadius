# Roadmap

This project was built in phases, each decomposed from the original project
brief and shipped as a working, non-mocked slice. This page collects the phase
plan and the current status in one place. It is the canonical overview; the
per-feature detail lives in the other files under [`docs/`](.).

Legend: ✅ done · 🚧 in progress · ⏳ planned

---

## Feature overview (interactive)

A visual, at-a-glance summary of everything the appliance offers — the auth data
flow (Horizon → RADIUS → FreeRADIUS → AD), the feature areas, and the container
stack — is published as a standalone page:

**https://claude.ai/code/artifact/3ef1f268-d325-4cfa-a20f-c2686b39b3e0**

It is a companion to this roadmap: the page shows *what* the appliance does, this
document tracks *when* each part landed.

---

## Phase 1 — Foundation ✅

The end-to-end base the rest builds on.

- Docker Compose stack: frontend (nginx), backend (FastAPI), FreeRADIUS
  (+ control agent), PostgreSQL.
- Local admin login: Argon2id hashing, session cookie (JWT) + double-submit
  CSRF, login lockout.
- RBAC roles: `administrator` / `operator` / `auditor`.
- Dashboard plus `/health`, `/ready` probes.
- Audit log and RADIUS live log (secrets masked).
- Hardened containers: non-root, `cap_drop: ALL`, `no-new-privileges`; RADIUS
  ports published only on the FreeRADIUS container.

## Phase 2 — RADIUS core management ✅

Real RADIUS client management with a safe configuration lifecycle.

- RADIUS clients + client groups (CRUD). Shared secrets encrypted at rest
  (Fernet).
- Config generator: database → FreeRADIUS config, deterministic and versioned.
- **Real** validation via `radiusd -XC`.
- **Real** reload with automatic rollback on failure.
- Configuration history with **view content, restore any earlier version, and
  delete** stored versions (the active version is protected). See
  [issue #28](https://github.com/kurdem/MyFreeRadius/issues/28).

## Phase 3 — Active Directory ✅

- **Slice 1:** AD configuration + **real** LDAP(S) connection test + allowed
  groups. See [`active-directory.md`](active-directory.md).
- **Slice 2:** FreeRADIUS ↔ AD auth wiring — generated `ldap` module +
  `manager` virtual server (PAP bind) + AD group authorization (`memberOf`).
- **CA certificate management** for LDAPS validation: upload (PEM / `.cer` /
  `.crt`), expiry warnings, applied to the connection test and the generated
  LDAP config.

## Phase 4 — MFA & Test Authentication ✅

- **TOTP MFA**: per-user enrollment (QR code), self-service enrollment link
  (one-time token + expiry). See [`mfa.md`](mfa.md).
- FreeRADIUS delegates authentication to the backend via `rlm_rest`.
- Two modes: `totp_only` and `ad_password_plus_totp` (AD password + OTP).
- Configurable OTP issuer (company name shown in the authenticator app), set
  under Branding.
- **Test Authentication**: real end-to-end Access-Request through the full
  pipeline (via `radclient`), run from the UI.

## Phase 5 — Backup / Restore & Setup Wizard ✅

- **Backup / restore** of the full configuration; secrets stay encrypted, with
  an optional passphrase. See [`backup.md`](backup.md).
- **Setup wizard** — guided first run: admin → AD → Horizon client → group →
  activate → test.

## Phase 6 — Monitoring / Metrics ✅

- Prometheus `/metrics` endpoint and deep `/health/detailed` component health.
- In-app Monitoring page.
- Optional `monitoring` compose profile: Prometheus + Grafana (provisioned
  datasource) with starter alert rules. See [`monitoring.md`](monitoring.md).

---

## Cross-cutting hardening ✅

Applied across phases rather than as a single milestone.

- BlastRADIUS mitigation (CVE-2024-3596) via Message-Authenticator, toggleable
  per client.
- Encryption of secrets and AD bind passwords at rest (Fernet).
- See [`security.md`](security.md).

---

## Planned / open ⏳

- **Authentication Policies** — a policy engine mapping RADIUS client groups +
  AD groups to allow/deny decisions and reply attributes. Currently shown in the
  UI as *Coming Soon*, never as fake functionality.

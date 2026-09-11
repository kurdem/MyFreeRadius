# Security

Security priority order for this project: **Security → Functionality →
Stability → Usability → Extensibility.**

## Secrets at rest

- RADIUS shared secrets (and, in Phase 3, AD bind passwords) are encrypted with
  **Fernet** (`FERNET_KEY`) before being stored in the database.
- Plaintext secrets are **never** returned by the API or UI (`has_secret` flag
  only), and are excluded from exports by default.
- The generated `clients.conf` necessarily contains secrets in cleartext
  (FreeRADIUS requires them). It lives only inside the FreeRADIUS container and
  the database; it is not exported.

## Web authentication (spec §21)

- Passwords hashed with **Argon2id** (`argon2-cffi`), with opportunistic rehash.
- **Login lockout**: after 5 consecutive failures an account is locked for
  15 minutes. Auth errors are generic (no user enumeration); a timing-equaliser
  hash runs on unknown users.
- Session is a signed **JWT in an httpOnly cookie** (not reachable from JS).
- **CSRF**: double-submit token — a readable `radiusmgr_csrf` cookie must be
  echoed in the `X-CSRF-Token` header on every state-changing request.
- `Secure` cookie flag and HSTS are enabled when `APP_ENV=prod`.

## RBAC (spec §22)

| Role | Capabilities |
|------|--------------|
| administrator | Full access (create/modify/activate/rollback) |
| operator | View config, view logs (no critical changes) |
| auditor | Read-only: logs, history |

Enforced server-side via dependencies on every endpoint; the UI hides actions
it cannot perform, but the backend is the authority.

## Injection defence (spec §26)

- Every value that reaches `clients.conf` is strictly validated:
  - **name**: `[A-Za-z0-9._-]` only.
  - **ipaddr**: parsed as a real IP address or CIDR network.
  - **shared secret**: printable ASCII, **no quotes, backslashes or whitespace**,
    so it cannot break out of the quoted config token or inject directives.
  - **nas_type**: allow-list.
- The config template quotes the secret; combined with the validation above,
  config/command injection through client fields is prevented.
- The control agent calls `subprocess` with an **argument list and
  `shell=False`** — no shell, ever. Untrusted input is never interpolated into
  a command line.

## Transport & process isolation

- The FreeRADIUS **control agent is internal only** (not published to the host)
  and requires a bearer token (`RADIUS_AGENT_TOKEN`).
- The backend never mounts the Docker socket and never runs `freeradius`
  itself.
- RADIUS UDP ports are published only on the FreeRADIUS service.

## Container hardening (spec §26)

- Backend and FreeRADIUS images run as a **non-root** user.
- Compose sets `no-new-privileges: true` and `cap_drop: ALL` where applicable.
- Multi-stage builds keep runtime images minimal.

## Logging & audit (spec §§13, 23)

- Structured JSON logs with an automatic masking filter for anything resembling
  a secret/password/token.
- The RADIUS log tail is masked by the control agent before it leaves the
  container.
- Every administrative change is written to the **audit log** (user, action,
  object, source IP, result) — **never** secrets or passwords.

## Responsible disclosure / hardening backlog

- Read-only root filesystems + tmpfs mounts (follow-up).
- Rate limiting at the edge / WAF (follow-up).
- OIDC/Entra ID and LDAP web-login (prepared for, Phase 21 extension).

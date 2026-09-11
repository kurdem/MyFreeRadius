# Architecture

## Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| Frontend | React + TypeScript + MUI, served by nginx | UI; proxies `/api` to backend on the same origin |
| Backend | FastAPI + SQLAlchemy + Pydantic | Config manager, validation, RBAC, audit, REST API |
| FreeRADIUS | `freeradius/freeradius-server:3.2` + control agent | RADIUS auth/acct + config validate/reload |
| Database | PostgreSQL (SQLite for local dev) | Persistent configuration & audit store |

```
Browser ──HTTPS──▶ nginx (frontend)
                      │ /api  (same origin: cookie + CSRF)
                      ▼
                  FastAPI backend ──▶ PostgreSQL
                      │ authenticated HTTP (internal docker network)
                      ▼
             FreeRADIUS container
               ├─ control agent  (:8000, internal only)
               └─ radiusd        (:1812/udp, :1813/udp)
```

## Why a control agent?

FreeRADIUS reads its client definitions from `clients.conf`. Changing them
requires the daemon to reload. Rather than give the backend privileges to
manage a process in another container (e.g. by mounting the Docker socket —
a large attack surface), a small **control agent** runs *inside* the
FreeRADIUS container and owns the `radiusd` process.

The backend calls the agent over the internal network with a shared bearer
token (`RADIUS_AGENT_TOKEN`). The agent exposes:

| Endpoint | Purpose |
|----------|---------|
| `POST /config/validate` | Write candidate → run `freeradius -XC` → restore current. The running server is never disturbed. |
| `POST /config/apply` | Validate → back up current → write → restart radiusd. Rolls back to the previous config if the restart fails. |
| `GET /status` | radiusd running state + version |
| `GET /logs?limit=` | Tail of the RADIUS log, secrets masked |
| `GET /health` | Unauthenticated container healthcheck |

The agent uses only the Python standard library (no pip packages) and never
passes untrusted input to a shell (`subprocess` with an argument list,
`shell=False`).

## Configuration lifecycle (source of truth = database)

```
DB (clients) ─▶ Config Generator (Jinja2, deterministic) ─▶ clients.conf
                                                              │
                                    ConfigVersion(PENDING) ◀──┘
                                                              │ validate (-XC)
                                                              │ activate
                             ACTIVE ◀── promote ── PENDING ───┘
                             PREVIOUS ◀── demote old ACTIVE
```

- Every generated config is stored as an immutable `ConfigVersion` with a
  SHA-256 checksum → meaningful history and diffs.
- Exactly one version is `ACTIVE`. The prior one is kept as `PREVIOUS` for
  rollback, so a failed activation can never destroy a known-good config.
- Generation is deterministic (clients sorted by name), so identical data
  yields byte-identical output.

## Data model

- `User` — local accounts, Argon2id hash, role, lockout state.
- `RadiusClient` — name, IP/CIDR, encrypted shared secret, NAS type, group.
- `ClientGroup` — named grouping (e.g. a Horizon cluster).
- `ConfigVersion` — versioned `clients.conf` snapshots + state.
- `AuditLog` — administrative actions (never secrets).

## API surface (`/api/v1`)

`/auth` · `/clients` · `/client-groups` · `/configuration` · `/logs/radius` ·
`/logs/audit` · `/dashboard` · `/health` · `/ready`

Interactive docs at `/docs` (OpenAPI/Swagger) when the backend runs.

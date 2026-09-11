# FreeRADIUS Manager

A Docker-based management appliance that lets Windows / VMware Horizon
administrators run and configure a FreeRADIUS server through a modern web
interface — without editing FreeRADIUS config files by hand.

Primary use case:

```
VMware Horizon Connection Server  ──RADIUS/1812──▶  FreeRADIUS  ──LDAP(S)──▶  Active Directory
```

> **Project status — Phases 1 & 2 implemented.**
> This repository currently delivers a working end-to-end base plus real RADIUS
> client management. Active Directory, authentication policies, certificate
> management and end-to-end auth tests are planned for later phases and are
> shown in the UI as **Coming Soon** (never as fake functionality).

---

## What works today (Phases 1 & 2)

| Area | Status |
|------|--------|
| Docker Compose stack (frontend, backend, FreeRADIUS, PostgreSQL) | ✅ |
| Local admin login (Argon2id, session cookies, CSRF, login lockout) | ✅ |
| RBAC roles (administrator / operator / auditor) | ✅ |
| RADIUS client CRUD + client groups | ✅ |
| Shared secrets encrypted at rest (Fernet) | ✅ |
| Config generator: DB → `clients.conf` (deterministic, versioned) | ✅ |
| **Real** validation via `freeradius -XC` | ✅ |
| **Real** reload with automatic rollback on failure | ✅ |
| Configuration history + rollback | ✅ |
| RADIUS live log + audit log (secrets masked) | ✅ |
| Dashboard + health/readiness endpoints | ✅ |
| Active Directory config + **real** LDAP(S) connection test + allowed groups | ✅ (Phase 3, slice 1) |
| FreeRADIUS ↔ AD auth wiring: generated `ldap` module + `manager` virtual server (PAP bind) + AD group authorization | ✅ (Phase 3, slice 2) |
| **TOTP MFA**: per-user enrollment (QR), FreeRADIUS delegates via `rlm_rest`, `totp_only` / `ad_password_plus_totp` modes | ✅ (Phase 4) |
| **Test Authentication**: real end-to-end Access-Request through the full pipeline (via `radclient`) | ✅ |
| **CA certificate management** for LDAPS validation (upload, expiry warnings, applied to the test + generated LDAP config) | ✅ |
| **Backup / restore** of the full configuration (secrets kept encrypted; optional passphrase) | ✅ (Phase 5) |
| Monitoring / metrics, setup wizard | ⏳ |
| End-to-end "Test Authentication" | ⏳ Phase 4 |
| Backup / restore, monitoring/metrics | ⏳ Phase 5–6 |

See [`docs/`](docs/) for architecture, security and Horizon guides.

---

## Architecture

```
Browser ──HTTPS──▶ Frontend (React/MUI, nginx)
                       │  /api  (same origin, cookie + CSRF)
                       ▼
                   Backend (FastAPI)
                       │  configuration manager · validation · RBAC · audit
                       ▼  authenticated HTTP (internal network)
             FreeRADIUS container
               ├─ control agent (validate / reload / logs)
               └─ radiusd (1812/udp, 1813/udp)
                       │
                       ▼  (Phase 3) LDAP/LDAPS
                 Active Directory
```

The backend never runs `freeradius` itself. A small **control agent** inside
the FreeRADIUS container owns the `radiusd` process and performs validation,
reload and rollback. This keeps privilege isolated and avoids mounting the
Docker socket. Details: [`docs/architecture.md`](docs/architecture.md).

---

## Quick start

Prerequisites: Docker + Docker Compose.

```bash
# 1. Configure secrets
cp .env.example .env

# Generate strong values:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('RADIUS_AGENT_TOKEN=' + secrets.token_urlsafe(32))"
# ...and set BOOTSTRAP_ADMIN_PASSWORD and POSTGRES_PASSWORD.

# 2. Build and start
docker compose build
docker compose up -d

# 3. Open the UI
#    http://localhost:8080   (login with the bootstrap admin credentials)
```

RADIUS is served on the host at `udp/1812` (auth) and `udp/1813` (accounting).

### First run in the UI

1. Log in as the bootstrap administrator.
2. **RADIUS Clients → Add Client** — add each Horizon Connection Server
   (name, IP, shared secret, NAS type = `vmware`).
3. **Configuration → Generate Candidate → Validate → Activate**.
4. **Logs** — watch RADIUS activity live.

---

## Local development

Backend (SQLite, no containers):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=dev FERNET_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
export BOOTSTRAP_ADMIN_PASSWORD=devpassword DATABASE_URL=sqlite:///./dev.db RADIUS_AGENT_TOKEN=dev
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:8080 (proxies /api to :8000)
```

### Tests

```bash
cd backend && pytest                       # backend unit/API/security tests
python freeradius/control_agent/test_agent.py   # control-agent logic (fake radiusd)
```

---

## Documentation

- [Architecture](docs/architecture.md)
- [Installation](docs/installation.md)
- [VMware Horizon integration](docs/horizon.md)
- [Active Directory](docs/active-directory.md)
- [Multi-Factor Authentication (TOTP)](docs/mfa.md)
- [Backup & Restore](docs/backup.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## Security highlights

- Shared secrets & (future) bind passwords encrypted at rest (Fernet); never
  returned in plaintext, never exported by default, never logged.
- Passwords hashed with **Argon2id**; login lockout; generic auth errors.
- Session in an httpOnly cookie + double-submit **CSRF** token.
- Strict input validation on every value that reaches the FreeRADIUS config
  (defends against config/command injection).
- `subprocess` is always called with an argument list and `shell=False`.
- Containers run non-root where possible, `no-new-privileges`, `cap_drop: ALL`.

Full details and threat notes: [`docs/security.md`](docs/security.md).

## License

See [LICENSE](LICENSE).

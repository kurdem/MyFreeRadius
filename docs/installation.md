# Installation

## Requirements

- Docker Engine 24+ and the Docker Compose plugin
- Outbound access to pull base images (Docker Hub) at build time
- Host UDP ports 1812 and 1813 free for RADIUS

## 1. Configure

```bash
cp .env.example .env
```

Generate strong secrets and set them in `.env`:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('RADIUS_AGENT_TOKEN=' + secrets.token_urlsafe(32))"
```

No Python at hand? Generate the same values with **OpenSSL** / shell tools:

```bash
echo "SECRET_KEY=$(openssl rand -base64 48 | tr '+/' '-_' | tr -d '=')"
# FERNET_KEY must be 32 url-safe base64 bytes (44 chars ending in '='):
echo "FERNET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')"
echo "RADIUS_AGENT_TOKEN=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
```

The `FERNET_KEY` is special: it must be a real Fernet key (32 url-safe base64
bytes, 44 characters ending in `=`). `tr '+/' '-_'` makes the OpenSSL output
url-safe; do not strip the trailing `=`. `token_urlsafe`/hex values are **not**
valid Fernet keys.

Also set `BOOTSTRAP_ADMIN_PASSWORD` and `POSTGRES_PASSWORD`. Set `APP_ENV=prod`
for any non-local deployment (hardens cookies and hides internal errors).

> **Never commit `.env`.** It is git-ignored. Only `.env.example` belongs in
> version control.

## 2. Build & start

```bash
docker compose build
docker compose up -d
docker compose ps
```

All four services should report healthy after ~30s.

## 3. First login

Open `http://<host>:8080` and log in with `BOOTSTRAP_ADMIN_USERNAME` /
`BOOTSTRAP_ADMIN_PASSWORD`. The admin account is created once, on first startup,
only if no users exist. **Change the password after first login.**

## Ports

| Port | Service | Exposure |
|------|---------|----------|
| 8080/tcp | Frontend (UI + API proxy) | Host (change via `FRONTEND_HTTP_PORT`) |
| 1812/udp | RADIUS authentication | Host |
| 1813/udp | RADIUS accounting | Host |
| 8000/tcp | Backend / control agent | Internal only |
| 5432/tcp | PostgreSQL | Internal only |

## TLS (recommended for production)

This phase serves the UI over HTTP on 8080. For production, terminate TLS in
front of the frontend (a reverse proxy such as Traefik/nginx/Caddy, or a load
balancer) and set `APP_ENV=prod` so session cookies are marked `Secure`.
Update `CORS_ORIGINS` to the HTTPS origin.

## Persistence

Named volumes:

- `db-data` — PostgreSQL data (clients, config history, audit log)
- `radius-logs` — FreeRADIUS logs

The database is the source of truth for the RADIUS configuration; the active
`clients.conf` can always be regenerated from it via **Configuration → Generate → Activate**.

## Upgrades

```bash
git pull
docker compose build
docker compose up -d
```

Schema is created automatically on start. (An Alembic migration chain will
manage schema changes as the model stabilises.)

## Backup (manual, until Phase 5)

```bash
docker compose exec database pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

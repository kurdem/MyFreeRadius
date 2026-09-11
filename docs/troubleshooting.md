# Troubleshooting

## Services

```bash
docker compose ps            # health of all services
docker compose logs backend
docker compose logs freeradius
docker compose logs frontend
```

## Cannot log in

- The bootstrap admin is created **only on first start and only if no users
  exist**. If you started before setting `BOOTSTRAP_ADMIN_PASSWORD`, set it and
  recreate the backend, or add a user manually.
- After 5 failed attempts the account locks for 15 minutes (by design).
- `401 Invalid username or password` is intentionally generic.

## "CSRF token missing or invalid" (403)

The SPA sends the `X-CSRF-Token` header automatically. If you call the API
directly, first `POST /api/v1/auth/login`, then send the value of the
`radiusmgr_csrf` cookie in the `X-CSRF-Token` header on POST/PUT/DELETE.

## Configuration won't activate

- **502 "control agent unreachable"** — the FreeRADIUS container/agent is down.
  Check `docker compose logs freeradius` and that the agent port 8000 is up
  inside the container (`GET /health`).
- **"Configuration invalid"** — the `details` field contains the
  `freeradius -XC` output (secrets masked). Fix the offending client and
  regenerate.
- A failed activation **keeps the previous working config** — RADIUS keeps
  serving. Use **Rollback** if needed.

## RADIUS rejects everything

- Confirm the client's IP matches the source IP FreeRADIUS sees
  (`docker compose logs freeradius`, Logs page).
- Confirm the shared secret matches on both sides.
- Until Active Directory is configured (Phase 3), there is no user backend, so
  real user logins will `Access-Reject`. This is expected — the RADIUS
  transport and client/secret can still be verified from the logs.

## No lines on the RADIUS Live Log

- Authentication logging is enabled in the image (`log { auth = yes }`). If you
  customised `radiusd.conf`, ensure `destination = files` and the log path
  matches `RADIUS_LOG_FILE` (`/var/log/radius/radius.log`).
- The `radius-logs` volume persists logs across restarts.

## Building the FreeRADIUS image

The control agent needs a minimal `python3` in the image (installed via apt in
`freeradius/Dockerfile`). The build must run where Docker Hub and the Debian
apt mirrors are reachable.

## Reset everything (destroys data)

```bash
docker compose down -v      # removes db-data and radius-logs volumes
```

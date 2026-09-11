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

- The control agent captures FreeRADIUS's own stdout/stderr into a ring buffer,
  so the Live Log does not depend on a specific file path. If it is empty, the
  agent returns a hint line telling you whether FreeRADIUS is running.
- An empty log usually just means **no RADIUS traffic yet** — lines appear once
  a request arrives (e.g. an `Access-Request` from a Connection Server). Send a
  test with `radclient` to confirm:
  ```bash
  echo "User-Name=test,User-Password=test" | \
    radclient -x <freeradius-host>:1812 auth <shared-secret>
  ```
- The image sets `log { destination = stdout; auth = yes }` so authentication
  results ("Login OK" / "Login incorrect") are captured. If you customised
  `radiusd.conf`, keep `destination = stdout` for the Live Log to work.
- Captured lines are also mirrored to `RADIUS_LOG_FILE`
  (`/var/log/radius/radius.log`) on the `radius-logs` volume for persistence.
- If the Live Log shows a 502/"control agent unreachable", the FreeRADIUS
  container or its agent is down — check `docker compose logs freeradius`.

## Building the FreeRADIUS image

The control agent needs a minimal `python3` in the image (installed via apt in
`freeradius/Dockerfile`). The build must run where Docker Hub and the Debian
apt mirrors are reachable.

## Reset everything (destroys data)

```bash
docker compose down -v      # removes db-data and radius-logs volumes
```

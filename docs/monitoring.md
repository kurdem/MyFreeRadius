# Monitoring & Metrics

The appliance exposes its runtime state in two ways: a human-facing **Monitoring**
page in the UI and a machine-readable **Prometheus** endpoint. An optional
Compose profile ships a ready-to-run Prometheus + Grafana stack with alert rules.

---

## 1. In-app Monitoring page

Sign in and open **Monitoring** in the left navigation. It calls
`GET /api/v1/health/detailed` (authenticated) and refreshes every 15 seconds,
showing per-component status:

| Component | OK | WARNING | CRITICAL |
|-----------|----|---------|----------|
| application | always | – | – |
| database | `SELECT 1` succeeds | – | query fails |
| freeradius | process running (via control agent) | – | not running / agent unreachable |
| certificates | none uploaded, or all valid | soonest CA expiry ≤ 30 days | a CA has expired |
| active_directory | enabled, or not configured | configured but disabled | – |

The overall status is the worst of the components.

---

## 2. Prometheus metrics endpoint

`GET /metrics` (unauthenticated, plain text, Prometheus exposition format) is
served at the backend root — inside the Compose network at
`http://backend:8000/metrics`. It is **not** proxied through the frontend, so it
is only reachable on the internal network (or however you choose to expose it).

Gauges are refreshed from the database and control agent on every scrape;
counters accumulate at runtime.

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `radiusmgr_info` | gauge | `version` | Build info (value always 1) |
| `radiusmgr_auth_total` | counter | `result` = `accept`/`reject` | RADIUS authorize calls (rlm_rest → backend) |
| `radiusmgr_test_total` | counter | `result` = `accept`/`reject` | Test-Authentication runs |
| `radiusmgr_config_activations_total` | counter | `result` = `success`/`failure` | Configuration activations |
| `radiusmgr_radius_clients` | gauge | `state` = `enabled`/`disabled` | RADIUS clients by state |
| `radiusmgr_active_config_version` | gauge | – | Currently active config version (0 = none) |
| `radiusmgr_certificates_total` | gauge | – | Stored CA certificates |
| `radiusmgr_certificate_days_left` | gauge | – | Days until the soonest CA expiry (large sentinel when none) |
| `radiusmgr_ad_enabled` | gauge | – | Active Directory enabled (1/0) |
| `radiusmgr_mfa_enabled` | gauge | – | MFA enabled (1/0) |
| `radiusmgr_freeradius_up` | gauge | – | FreeRADIUS reachable and running (1/0) |
| `radiusmgr_users_total` | gauge | – | Local web users |

---

## 3. Optional Prometheus + Grafana stack

The `monitoring` Compose profile adds two extra services. They are **off by
default** and only start when the profile is requested:

```bash
docker compose --profile monitoring up -d
```

This starts:

- **Prometheus** on `${PROMETHEUS_PORT:-9090}`, scraping `backend:8000/metrics`
  every 30s and loading the alert rules.
- **Grafana** on `${GRAFANA_PORT:-3000}`, pre-provisioned with Prometheus as the
  default datasource.

Configure the host ports and Grafana admin password in `.env`:

```env
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
GRAFANA_ADMIN_PASSWORD=change-me
```

Log in to Grafana as `admin` with `GRAFANA_ADMIN_PASSWORD` and build dashboards
against the metrics above. Stop only the monitoring services with:

```bash
docker compose --profile monitoring stop prometheus grafana
```

### Files

| File | Purpose |
|------|---------|
| `monitoring/prometheus.yml` | Scrape + rule config |
| `monitoring/alerts.yml` | Alert rules (see below) |
| `monitoring/grafana/provisioning/datasources/datasource.yml` | Grafana datasource |

---

## 4. Alert rules

`monitoring/alerts.yml` defines starting-point alerts:

| Alert | Severity | Fires when |
|-------|----------|------------|
| `FreeRadiusDown` | critical | `radiusmgr_freeradius_up == 0` for 2m |
| `BackendDown` | critical | scrape target down for 2m |
| `CaCertificateExpiringSoon` | warning | soonest CA expiry within 0–30 days for 1h |
| `CaCertificateExpired` | critical | a CA has expired for 5m |
| `HighAuthRejectRate` | warning | > 50 % of RADIUS authorizations rejected over 10m, for 15m |

Wire these to Alertmanager (not bundled) to deliver notifications.

---

## 5. Health probes (no auth)

For load balancers / orchestrators, two unauthenticated probes remain available:

- `GET /health` — liveness (always cheap).
- `GET /ready` — readiness (database reachable).

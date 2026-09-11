"""Prometheus metrics (monitoring MVP).

Counters are incremented at runtime; gauges are refreshed from the database (and
the FreeRADIUS control agent) each time /metrics is scraped. A dedicated
registry keeps the output self-contained and free of default process metrics
noise, while still exposing app info.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, generate_latest

from app import __version__

registry = CollectorRegistry()

# --- counters (runtime) ---------------------------------------------------- #
AUTH_TOTAL = Counter(
    "radiusmgr_auth_total", "RADIUS authorize (rlm_rest) results", ["result"], registry=registry
)
TEST_TOTAL = Counter(
    "radiusmgr_test_total", "Test Authentication results", ["result"], registry=registry
)
ACTIVATION_TOTAL = Counter(
    "radiusmgr_config_activations_total", "Configuration activations", ["result"], registry=registry
)

# --- gauges (refreshed on scrape) ------------------------------------------ #
INFO = Gauge("radiusmgr_info", "Build info", ["version"], registry=registry)
CLIENTS = Gauge("radiusmgr_radius_clients", "RADIUS clients by state", ["state"], registry=registry)
ACTIVE_VERSION = Gauge("radiusmgr_active_config_version", "Active config version", registry=registry)
CERTS = Gauge("radiusmgr_certificates_total", "Stored CA certificates", registry=registry)
CERT_DAYS = Gauge(
    "radiusmgr_certificate_days_left", "Days until the soonest CA certificate expires", registry=registry
)
AD_ENABLED = Gauge("radiusmgr_ad_enabled", "Active Directory enabled (1/0)", registry=registry)
MFA_ENABLED = Gauge("radiusmgr_mfa_enabled", "MFA enabled (1/0)", registry=registry)
FREERADIUS_UP = Gauge("radiusmgr_freeradius_up", "FreeRADIUS reachable and running (1/0)", registry=registry)
USERS = Gauge("radiusmgr_users_total", "Local web users", registry=registry)


def refresh(db) -> None:
    """Update the gauges from current state. Imports are local to avoid cycles."""
    from sqlalchemy import func, select

    from app.models import (
        ADConfig,
        CaCertificate,
        ConfigState,
        ConfigVersion,
        RadiusClient,
        User,
    )
    from app.services import cert_service, radius_agent
    from app.services.radius_agent import AgentError

    INFO.labels(version=__version__).set(1)

    total = db.scalar(select(func.count(RadiusClient.id))) or 0
    enabled = db.scalar(select(func.count(RadiusClient.id)).where(RadiusClient.enabled.is_(True))) or 0
    CLIENTS.labels(state="enabled").set(enabled)
    CLIENTS.labels(state="disabled").set(total - enabled)

    active = db.scalar(select(ConfigVersion.version).where(ConfigVersion.state == ConfigState.ACTIVE))
    ACTIVE_VERSION.set(active or 0)

    certs = db.scalars(select(CaCertificate)).all()
    CERTS.set(len(certs))
    if certs:
        CERT_DAYS.set(min(cert_service.status_for(c.not_after)[1] for c in certs))
    else:
        # No certificates uploaded -> nothing to warn about. Use a large sentinel
        # so the "expiring"/"expired" alert thresholds never trigger.
        CERT_DAYS.set(36500)

    ad = db.get(ADConfig, 1)
    AD_ENABLED.set(1 if (ad and ad.enabled) else 0)
    MFA_ENABLED.set(1 if (ad and ad.enabled and ad.mfa_enabled) else 0)

    USERS.set(db.scalar(select(func.count(User.id))) or 0)

    try:
        st = radius_agent.status()
        FREERADIUS_UP.set(1 if st.get("running") else 0)
    except AgentError:
        FREERADIUS_UP.set(0)


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST

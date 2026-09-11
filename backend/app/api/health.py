"""Health / readiness / dashboard endpoints (spec sections 19, 20)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ADConfig, CaCertificate, ConfigState, ConfigVersion, RadiusClient, User
from app.security.deps import require_any
from app.services import cert_service
from app.services import radius_agent
from app.services.radius_agent import AgentError

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness probe - always cheap, no external dependencies."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe - DB reachable."""
    try:
        db.execute(select(1))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ready" if db_ok else "degraded", "database": db_ok}


@router.get("/health/detailed")
def health_detailed(db: Session = Depends(get_db), _: User = Depends(require_any)):
    """Per-component health with OK / WARNING / CRITICAL (spec section 20)."""
    components: list[dict] = [{"name": "application", "status": "OK"}]

    # Database
    try:
        db.execute(select(1))
        components.append({"name": "database", "status": "OK"})
    except Exception as exc:  # noqa: BLE001
        components.append({"name": "database", "status": "CRITICAL", "detail": str(exc)[:120]})

    # FreeRADIUS control agent + process
    try:
        st = radius_agent.status()
        running = bool(st.get("running"))
        components.append({
            "name": "freeradius",
            "status": "OK" if running else "CRITICAL",
            "detail": st.get("version") or ("running" if running else "not running"),
        })
    except AgentError as exc:
        components.append({"name": "freeradius", "status": "CRITICAL", "detail": str(exc)[:120]})

    # Certificates (soonest expiry)
    certs = db.scalars(select(CaCertificate)).all()
    if not certs:
        components.append({"name": "certificates", "status": "OK", "detail": "none uploaded"})
    else:
        worst, days = "OK", None
        for c in certs:
            s, d = cert_service.status_for(c.not_after)
            days = d if days is None else min(days, d)
            if s == "expired":
                worst = "CRITICAL"
            elif s == "expiring" and worst != "CRITICAL":
                worst = "WARNING"
        components.append({"name": "certificates", "status": worst, "detail": f"min {days} days left"})

    # Active Directory (configuration state, not a live bind)
    ad = db.get(ADConfig, 1)
    if ad is None:
        components.append({"name": "active_directory", "status": "OK", "detail": "not configured"})
    else:
        components.append({
            "name": "active_directory",
            "status": "OK" if ad.enabled else "WARNING",
            "detail": ad.domain + (" (enabled)" if ad.enabled else " (disabled)"),
        })

    order = {"OK": 0, "WARNING": 1, "CRITICAL": 2}
    overall = max((c["status"] for c in components), key=lambda s: order[s])
    return {"status": overall, "components": components}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_any)):
    """Aggregate status for the dashboard (spec section 19)."""
    total_clients = db.scalar(select(func.count(RadiusClient.id))) or 0
    enabled_clients = (
        db.scalar(select(func.count(RadiusClient.id)).where(RadiusClient.enabled.is_(True))) or 0
    )
    active_version = db.scalar(
        select(ConfigVersion.version).where(ConfigVersion.state == ConfigState.ACTIVE)
    )

    radius_status: dict = {"reachable": False}
    try:
        radius_status = radius_agent.status()
        radius_status["reachable"] = True
    except AgentError as exc:
        radius_status = {"reachable": False, "error": str(exc)}

    ad = db.get(ADConfig, 1)
    if ad is None:
        ad_status = {"status": "not_configured", "note": "Configure under Active Directory"}
    else:
        ad_status = {
            "status": "configured" if ad.enabled else "disabled",
            "domain": ad.domain,
            "note": "AD auth active once configuration is activated"
            if ad.enabled else "AD is configured but disabled",
        }

    certs = db.scalars(select(CaCertificate)).all()
    if not certs:
        cert_status = {"status": "none", "count": 0, "note": "No CA certificates uploaded"}
    else:
        worst = "valid"
        min_days = None
        for c in certs:
            st, days = cert_service.status_for(c.not_after)
            min_days = days if min_days is None else min(min_days, days)
            if st == "expired":
                worst = "expired"
            elif st == "expiring" and worst != "expired":
                worst = "expiring"
        cert_status = {"status": worst, "count": len(certs), "min_days_left": min_days}

    return {
        "radius": radius_status,
        "clients": {"total": total_clients, "enabled": enabled_clients,
                    "disabled": total_clients - enabled_clients},
        "active_config_version": active_version,
        "active_directory": ad_status,
        "certificates": cert_status,
    }

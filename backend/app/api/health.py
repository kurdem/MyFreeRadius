"""Health / readiness / dashboard endpoints (spec sections 19, 20)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ADConfig, ConfigState, ConfigVersion, RadiusClient, User
from app.security.deps import require_any
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
            "note": "RADIUS auth against AD is wired in the next slice",
        }

    return {
        "radius": radius_status,
        "clients": {"total": total_clients, "enabled": enabled_clients,
                    "disabled": total_clients - enabled_clients},
        "active_config_version": active_version,
        "active_directory": ad_status,
        # Phase 3 (certificates) surfaced as not-yet-available rather than faked.
        "certificates": {"status": "not_configured", "note": "Coming in phase 3"},
    }

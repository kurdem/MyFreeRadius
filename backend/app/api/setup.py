"""First-run setup wizard status (spec section 38).

The wizard itself is driven by the frontend, reusing the existing endpoints
(auth, active-directory, clients, configuration, radius). This provides a
completion flag and a derived checklist so the UI can show progress and steer
the operator to the next step.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ADConfig,
    ADGroup,
    AppState,
    ConfigState,
    ConfigVersion,
    RadiusClient,
    User,
)
from app.security.deps import require_admin, require_any
from app.services import audit

router = APIRouter(prefix="/setup", tags=["setup"])


def _state(db: Session) -> AppState:
    st = db.get(AppState, 1)
    if st is None:
        st = AppState(id=1, setup_completed=False)
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(require_any)):
    st = _state(db)
    ad = db.get(ADConfig, 1)
    return {
        "setup_completed": st.setup_completed,
        "checklist": {
            "administrator": (db.scalar(select(func.count(User.id))) or 0) > 0,
            "active_directory": ad is not None and ad.enabled,
            "radius_clients": (db.scalar(select(func.count(RadiusClient.id))) or 0) > 0,
            "ad_groups": (db.scalar(select(func.count(ADGroup.id))) or 0) > 0,
            "config_activated": db.scalar(
                select(func.count(ConfigVersion.id)).where(
                    ConfigVersion.state == ConfigState.ACTIVE
                )
            ) > 0,
        },
    }


@router.post("/complete")
def complete(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    st = _state(db)
    st.setup_completed = True
    db.commit()
    audit.record(
        db, username=user.username, action="SETUP_COMPLETED",
        source_ip=request.client.host if request.client else None,
    )
    return {"setup_completed": True}


@router.post("/reset")
def reset(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Re-open the wizard (does not change any configuration)."""
    st = _state(db)
    st.setup_completed = False
    db.commit()
    audit.record(
        db, username=user.username, action="SETUP_REOPENED",
        source_ip=request.client.host if request.client else None,
    )
    return {"setup_completed": False}

"""Prometheus scrape endpoint (monitoring MVP).

Exposed at /metrics (not under /api/v1) and unauthenticated, like a container
probe - it is scraped over the internal network and exposes only counts/gauges,
never secrets.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def prometheus_metrics(db: Session = Depends(get_db)):
    try:
        metrics.refresh(db)
    except Exception:  # noqa: BLE001 - never fail the scrape on a refresh error
        pass
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)

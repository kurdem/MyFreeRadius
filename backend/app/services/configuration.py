"""Configuration lifecycle service: generate, validate, activate, rollback.

Implements the safety guarantees from spec sections 15/16:

* a new candidate is stored as PENDING and validated before activation;
* the previously working configuration is retained (PREVIOUS) so a failed
  activation never destroys a known-good config;
* activation is atomic from the app's perspective - the agent validates again
  and rolls back on reload failure.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConfigState, ConfigVersion
from app.services import config_generator, radius_agent


class ConfigError(RuntimeError):
    pass


def _next_version(db: Session) -> int:
    current_max = db.scalar(select(func.max(ConfigVersion.version))) or 0
    return current_max + 1


def get_active(db: Session) -> ConfigVersion | None:
    return db.scalar(select(ConfigVersion).where(ConfigVersion.state == ConfigState.ACTIVE))


def generate_pending(db: Session, *, author: str, summary: str | None = None) -> ConfigVersion:
    """Render the current DB state into a new PENDING version.

    If the rendered content is identical to the ACTIVE version, no new version
    is created and the active one is returned unchanged.
    """
    version_no = _next_version(db)
    bundle = config_generator.generate_bundle(db, version=version_no)
    content = json.dumps(bundle)
    checksum = config_generator.bundle_checksum(bundle)

    active = get_active(db)
    if active is not None and active.checksum == checksum:
        return active

    # Clear any stale pending versions - only one pending at a time.
    for stale in db.scalars(
        select(ConfigVersion).where(ConfigVersion.state == ConfigState.PENDING)
    ):
        db.delete(stale)

    pending = ConfigVersion(
        version=version_no,
        state=ConfigState.PENDING,
        content=content,
        checksum=checksum,
        change_summary=summary,
        author=author,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


def _bundle(version: ConfigVersion) -> tuple[dict, list]:
    data = json.loads(version.content)
    return data.get("files", {}), data.get("deletes", [])


def validate(version: ConfigVersion) -> dict:
    files, deletes = _bundle(version)
    return radius_agent.validate_config(files, deletes)


def activate(db: Session, version: ConfigVersion) -> dict:
    """Apply ``version`` to FreeRADIUS and update version states on success."""
    from app.services import metrics

    files, deletes = _bundle(version)
    result = radius_agent.apply_config(files, deletes)
    if not result.get("success"):
        version.state = ConfigState.FAILED
        db.commit()
        metrics.ACTIVATION_TOTAL.labels(result="failure").inc()
        return result

    # Demote the current active version, promote this one.
    active = get_active(db)
    if active is not None and active.id != version.id:
        active.state = ConfigState.PREVIOUS
    version.state = ConfigState.ACTIVE
    db.commit()
    metrics.ACTIVATION_TOTAL.labels(result="success").inc()
    return result


def rollback(db: Session, *, author: str) -> ConfigVersion:
    """Re-activate the most recent PREVIOUS version."""
    previous = db.scalar(
        select(ConfigVersion)
        .where(ConfigVersion.state == ConfigState.PREVIOUS)
        .order_by(ConfigVersion.version.desc())
    )
    if previous is None:
        raise ConfigError("No previous configuration available to roll back to.")

    # Create a fresh version entry from the previous content to preserve history.
    version_no = _next_version(db)
    restored = ConfigVersion(
        version=version_no,
        state=ConfigState.PENDING,
        content=previous.content,
        checksum=previous.checksum,
        change_summary=f"Rollback to version {previous.version}",
        author=author,
    )
    db.add(restored)
    db.commit()
    db.refresh(restored)

    result = activate(db, restored)
    if not result.get("success"):
        raise ConfigError(result.get("message", "Rollback activation failed"))
    return restored

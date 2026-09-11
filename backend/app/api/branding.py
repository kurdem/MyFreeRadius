"""Branding: logo + application title (issue #20).

GET endpoints are public so the login page can render the branding before a user
is authenticated. Changing the branding requires an administrator.
"""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    File,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BrandingConfig, User
from app.security.deps import require_admin
from app.services import audit

router = APIRouter(prefix="/branding", tags=["branding"])

_DEFAULT_TITLE = "FreeRADIUS Manager"
_MAX_LOGO_BYTES = 2_000_000
_ALLOWED_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
}


def _get(db: Session) -> BrandingConfig | None:
    return db.get(BrandingConfig, 1)


@router.get("")
def get_branding(db: Session = Depends(get_db)):
    """Public: title + whether a logo is set (for the app bar and login page)."""
    b = _get(db)
    return {
        "app_title": b.app_title if b else _DEFAULT_TITLE,
        "has_logo": bool(b and b.logo),
    }


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    """Public: the logo image, if one is set."""
    b = _get(db)
    if not b or not b.logo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No logo set")
    return Response(content=b.logo, media_type=b.logo_content_type or "image/png",
                    headers={"Cache-Control": "no-cache"})


@router.put("")
async def update_branding(
    request: Request,
    app_title: str = Form(""),
    logo: UploadFile | None = File(default=None),
    remove_logo: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    b = _get(db)
    if b is None:
        b = BrandingConfig(id=1, app_title=_DEFAULT_TITLE)
        db.add(b)

    if app_title.strip():
        b.app_title = app_title.strip()[:120]

    if remove_logo:
        b.logo = None
        b.logo_content_type = None
    elif logo is not None:
        ctype = (logo.content_type or "").lower()
        if ctype not in _ALLOWED_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image type (use PNG, JPEG, GIF, WEBP or SVG)",
            )
        raw = await logo.read(_MAX_LOGO_BYTES + 1)
        if len(raw) > _MAX_LOGO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Logo too large (max 2 MB)")
        b.logo = raw
        b.logo_content_type = ctype

    db.commit()
    audit.record(
        db, username=user.username, action="UPDATE_BRANDING",
        source_ip=request.client.host if request.client else None,
    )
    return {"app_title": b.app_title, "has_logo": bool(b.logo)}

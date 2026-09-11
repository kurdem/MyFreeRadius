"""CA certificate management endpoints (spec section 11)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CaCertificate, User
from app.schemas.certificate import CertOut, CertUpload
from app.security.deps import require_admin, require_any
from app.services import audit, cert_service

router = APIRouter(prefix="/certificates", tags=["certificates"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(cert: CaCertificate) -> CertOut:
    st, days = cert_service.status_for(cert.not_after)
    return CertOut(
        id=cert.id, name=cert.name, subject=cert.subject, issuer=cert.issuer,
        fingerprint_sha256=cert.fingerprint_sha256,
        not_before=cert.not_before, not_after=cert.not_after,
        status=st, days_left=days,
    )


@router.get("", response_model=list[CertOut])
def list_certificates(db: Session = Depends(get_db), _: User = Depends(require_any)):
    certs = db.scalars(select(CaCertificate).order_by(CaCertificate.name)).all()
    return [_to_out(c) for c in certs]


@router.post("", response_model=CertOut, status_code=status.HTTP_201_CREATED)
def upload_certificate(
    payload: CertUpload,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        meta = cert_service.parse_certificate(payload.pem)
    except cert_service.CertificateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if db.scalar(select(CaCertificate).where(
        CaCertificate.fingerprint_sha256 == meta["fingerprint_sha256"]
    )):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This certificate is already stored")

    cert = CaCertificate(name=payload.name, pem=payload.pem.strip(), **meta)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    audit.record(
        db, username=user.username, action="UPLOAD_CA_CERT",
        object_ref=cert.subject[:120], source_ip=_client_ip(request),
    )
    return _to_out(cert)


@router.get("/{cert_id}/pem")
def get_pem(cert_id: int, db: Session = Depends(get_db), _: User = Depends(require_any)):
    cert = db.get(CaCertificate, cert_id)
    if not cert:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return Response(content=cert.pem, media_type="application/x-pem-file")


@router.delete("/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_certificate(
    cert_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    cert = db.get(CaCertificate, cert_id)
    if not cert:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    subject = cert.subject
    db.delete(cert)
    db.commit()
    audit.record(
        db, username=user.username, action="DELETE_CA_CERT",
        object_ref=subject[:120], source_ip=_client_ip(request),
    )

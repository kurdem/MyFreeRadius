"""Real LDAP/LDAPS connectivity test against Active Directory (spec section 6).

This performs an actual bind (and an optional base-DN read) so the UI's
"Test Connection" is not a mock. Passwords are never logged.
"""
from __future__ import annotations

import logging

from app.models import ADConfig
from app.security.crypto import decrypt_secret

logger = logging.getLogger("ldap")


def test_connection(config: ADConfig) -> dict:
    """Attempt to bind to the domain controller and read the base DN.

    Returns ``{"success": bool, "message": str, "details": str}``.
    """
    # Imported lazily so the rest of the app runs even if ldap3 is missing.
    try:
        from ldap3 import BASE, Connection, Server, Tls
        from ldap3.core.exceptions import LDAPException
    except ImportError:  # pragma: no cover - dependency always present in image
        return {
            "success": False,
            "message": "LDAP client library not available",
            "details": "Install ldap3 in the backend image.",
        }

    import ssl

    tls = None
    if config.use_ldaps:
        validate = ssl.CERT_REQUIRED if config.verify_tls else ssl.CERT_NONE
        tls = Tls(validate=validate)

    password = decrypt_secret(config.bind_password_encrypted)
    results: list[str] = []
    last_error: str | None = None

    # Try primary, then secondary DC.
    hosts = [h for h in (config.primary_dc, config.secondary_dc) if h]
    for host in hosts:
        try:
            server = Server(
                host,
                port=config.port,
                use_ssl=config.use_ldaps,
                tls=tls,
                connect_timeout=config.timeout_seconds,
            )
            conn = Connection(
                server,
                user=config.bind_user,
                password=password,
                auto_bind=True,
                receive_timeout=config.timeout_seconds,
            )
            results.append(f"{host}: bind OK")
            # Verify the base DN is readable (no user input in the filter).
            ok = conn.search(
                search_base=config.base_dn,
                search_filter="(objectClass=*)",
                search_scope=BASE,
                attributes=["distinguishedName"],
            )
            results.append(
                f"{host}: base DN {'readable' if ok else 'NOT readable'}"
            )
            conn.unbind()
            return {
                "success": True,
                "message": f"Connected to {host} and bound successfully.",
                "details": "\n".join(results),
            }
        except LDAPException as exc:
            last_error = f"{host}: {exc}"
            results.append(last_error)
            logger.warning("ldap_test_failed", extra={"event": "ldap_test", "result": host})
        except Exception as exc:  # noqa: BLE001 - surface any connection error
            last_error = f"{host}: {exc}"
            results.append(last_error)

    return {
        "success": False,
        "message": "Could not connect/bind to any domain controller.",
        "details": "\n".join(results) if results else (last_error or "unknown error"),
    }

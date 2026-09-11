"""Structured JSON logging with automatic masking of sensitive values.

Passwords and shared secrets must never reach the logs (spec sections 6, 12,
13, 23). We do two things:

* emit structured JSON records, and
* run every formatted message through a regex filter that redacts values of
  well-known sensitive keys.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

# Matches ``secret=...`` / ``"password": "..."`` style fragments.
_SENSITIVE_KEYS = (
    "password",
    "passwd",
    "secret",
    "shared_secret",
    "bind_password",
    "token",
    "private_key",
    "authorization",
)
_SENSITIVE_RE = re.compile(
    r'(?i)(' + "|".join(_SENSITIVE_KEYS) + r')(["\']?\s*[:=]\s*["\']?)([^",\'}\s]+)'
)


def _mask(text: str) -> str:
    return _SENSITIVE_RE.sub(r"\1\2***REDACTED***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _mask(record.getMessage()),
        }
        for key in ("event", "user", "client_ip", "action", "result", "object"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = _mask(str(value))
        if record.exc_info:
            payload["exc"] = _mask(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorn access logs are noisy and may contain query strings; keep warnings+.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

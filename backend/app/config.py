"""Application configuration loaded from environment variables.

All settings are read once at startup via :class:`Settings`. Secrets are never
logged; see :mod:`app.logging_conf` for the masking filter.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    app_env: str = Field(default="dev")
    tz: str = Field(default="UTC")

    # Security
    secret_key: str = Field(default="dev-insecure-secret-change-me")
    fernet_key: str = Field(default="")
    session_ttl_minutes: int = Field(default=480)
    cors_origins: str = Field(default="http://localhost:8080")

    # Bootstrap admin
    bootstrap_admin_username: str = Field(default="admin")
    bootstrap_admin_password: str = Field(default="")

    # Database
    database_url: str = Field(default="sqlite:////data/radiusmgr.db")

    # FreeRADIUS control agent
    radius_agent_url: str = Field(default="http://freeradius:8000")
    radius_agent_token: str = Field(default="")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("session_ttl_minutes")
    @classmethod
    def _positive_ttl(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("SESSION_TTL_MINUTES must be positive")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

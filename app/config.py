"""Application configuration, read from environment variables.

Every environment (local, staging, production) uses the same code; only the
environment variables differ. See ``.env.example`` for the full list.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import ClassVar

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    """Read a true/false environment variable ("true", "1", "yes" count as true)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_str(name: str, default: str = "") -> str:
    """Read a string environment variable; a blank value counts as unset."""
    value = os.environ.get(name, "").strip()
    return value or default


def normalize_database_url(url: str) -> str:
    """Point PostgreSQL URLs at the psycopg 3 driver.

    Hosting providers often hand out ``postgres://`` or ``postgresql://`` URLs;
    SQLAlchemy needs ``postgresql+psycopg://`` to use psycopg 3.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Config:
    """Settings shared by every environment."""

    APP_ENV = env_str("APP_ENV", "local")
    SECRET_KEY = env_str("SECRET_KEY") or None
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        env_str("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'fleet.db'}")
    )
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict] = {"pool_pre_ping": True}

    # Branding. The public repo ships a fictional provider; set PROVIDER_NAME to
    # show a real company name during a private demo.
    PROVIDER_NAME = env_str("PROVIDER_NAME", "High Plains Compliance Co.")

    # Demo mode turns on the one-click role switcher on the login page and lets
    # the Motive client return mock data. Never enable it in production.
    DEMO_MODE = env_bool("DEMO_MODE", default=False)

    # Motive (ELD) credentials. Read from the environment only, never hard-coded.
    MOTIVE_API_KEY = env_str("MOTIVE_API_KEY")

    UPLOAD_FOLDER = env_str("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB spreadsheet limit

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)
    WTF_CSRF_TIME_LIMIT = None  # tie CSRF tokens to the session, not a timer


class TestConfig(Config):
    """Settings for pytest: in-memory database, fixed secret, demo mode on."""

    TESTING = True
    SECRET_KEY = "test-secret-key"  # noqa: S105 - test only
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    DEMO_MODE = True
    WTF_CSRF_ENABLED = False


def resolve_secret_key(config: dict) -> str:
    """Return the configured secret key, or a throwaway one for local use.

    Staging and production must set SECRET_KEY; starting without it is an error.
    Locally, a random key is generated so the app still runs (sessions reset on
    every restart).
    """
    key = config.get("SECRET_KEY")
    if key:
        return key
    if config.get("APP_ENV") in {"staging", "production"}:
        raise RuntimeError("SECRET_KEY must be set in staging and production.")
    return secrets.token_hex(32)

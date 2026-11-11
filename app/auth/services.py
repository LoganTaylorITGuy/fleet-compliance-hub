"""Auth helpers: passwords, user lookup, and which tenant a request runs as."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import g, session
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import Tenant, User
from ..permissions import is_provider
from ..tenancy import NO_ACCESS, TenantScope

ACTIVE_TENANT_KEY = "active_tenant_id"

# Demo personas for the login-page switcher. The seed script creates these
# users; their shared password is documented in the README.
DEMO_PERSONAS = {
    "provider_admin": ("admin@demo.example", "Provider Admin", "Compliance staff, all carriers"),
    "provider_limited": ("shop@demo.example", "Provider Limited", "Trailer shop, maintenance only"),
    "carrier_admin": ("owner@demo.example", "Carrier Admin", "Owner of one carrier"),
    "carrier_viewer": ("viewer@demo.example", "Carrier Viewer", "Read-only carrier login"),
}

# A real hash computed once, so failed logins for unknown emails take as long
# as wrong passwords (no user enumeration by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def find_user_by_email(email: str) -> User | None:
    return db.session.scalars(
        select(User).where(func.lower(User.email) == email.strip().lower())
    ).first()


def authenticate(email: str, password: str) -> User | None:
    user = find_user_by_email(email)
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return None
    if not user.active or not check_password_hash(user.password_hash, password):
        return None
    return user


def load_user(user_id: str) -> User | None:
    if not user_id.isdigit():
        return None
    user = db.session.scalars(select(User).where(User.id == int(user_id))).first()
    return user if user and user.active else None


def provider_tenants(user: User) -> list[Tenant]:
    """Tenants a provider user may switch between, ordered by name."""
    return list(
        db.session.scalars(
            select(Tenant).where(Tenant.provider_id == user.provider_id).order_by(Tenant.name)
        )
    )


def tenant_for_provider(user: User, tenant_id: int) -> Tenant | None:
    return db.session.scalars(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.provider_id == user.provider_id)
    ).first()


def resolve_scope(user) -> tuple[TenantScope, Tenant | None]:
    """Work out which tenant this request runs as.

    Carrier users: always their own tenant. Provider users: the tenant picked
    in the switcher, if it belongs to their provider. Everyone else: no access.
    """
    if not user.is_authenticated:
        return NO_ACCESS, None
    if is_provider(user):
        tenant_id = session.get(ACTIVE_TENANT_KEY)
        tenant = tenant_for_provider(user, tenant_id) if isinstance(tenant_id, int) else None
        if tenant is None:
            session.pop(ACTIVE_TENANT_KEY, None)
            return NO_ACCESS, None
        return TenantScope(tenant_id=tenant.id), tenant
    tenant = db.session.scalars(select(Tenant).where(Tenant.id == user.tenant_id)).first()
    return TenantScope(tenant_id=user.tenant_id), tenant


def active_tenant() -> Tenant | None:
    return g.get("active_tenant")


def safe_next_url(target: str | None) -> str | None:
    """Only allow same-site relative redirects after login (no open redirect)."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target

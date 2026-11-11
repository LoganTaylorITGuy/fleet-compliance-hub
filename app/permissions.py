"""Who can see and change what. One table, read by views, templates and tests.

Tenant isolation (which carrier's rows you see) lives in ``app/tenancy.py``.
This module covers the other axis: which *areas* a role may view or edit.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from flask import abort
from flask_login import current_user

from .models import Role

if TYPE_CHECKING:
    from .models import User

# Feature areas. Provider Limited users get a subset via User.permissions.
AREAS = (
    "dashboard",
    "drivers",
    "fleet",
    "maintenance",
    "hos",
    "training",
    "imports",
    "integrations",
    "audit",
)

# Areas a Provider Limited user always sees (read only) to find their way around.
LIMITED_BASE_VIEW = {"dashboard"}

# Areas that pull in another for viewing: trailer shop staff need the Fleet
# pages to reach maintenance records; academy staff need driver names.
VIEW_IMPLIES = {"maintenance": {"fleet"}, "training": {"drivers"}}

ADMIN_ONLY_VIEW = {"imports", "integrations", "audit"}


def is_provider(user: User) -> bool:
    return user.role in (Role.PROVIDER_ADMIN, Role.PROVIDER_LIMITED)


def limited_areas(user: User) -> set[str]:
    granted = {a.strip() for a in (user.permissions or "").split(",") if a.strip()}
    return granted & set(AREAS)


def can_view(user: User, area: str) -> bool:
    if not user.is_authenticated:
        return False
    match user.role:
        case Role.PROVIDER_ADMIN | Role.CARRIER_ADMIN:
            return True
        case Role.CARRIER_VIEWER:
            return area not in ADMIN_ONLY_VIEW
        case Role.PROVIDER_LIMITED:
            granted = limited_areas(user)
            implied = set().union(*(VIEW_IMPLIES.get(a, set()) for a in granted))
            return area in granted | implied | LIMITED_BASE_VIEW
    return False


def can_edit(user: User, area: str) -> bool:
    if not user.is_authenticated:
        return False
    match user.role:
        case Role.PROVIDER_ADMIN | Role.CARRIER_ADMIN:
            return True
        case Role.PROVIDER_LIMITED:
            return area in limited_areas(user)
    return False  # Carrier Viewer is read only


def require_view(area: str) -> Callable:
    """View decorator: 403 unless the current user may view ``area``."""
    return _require(area, can_view)


def require_edit(area: str) -> Callable:
    """View decorator: 403 unless the current user may edit ``area``."""
    return _require(area, can_edit)


def _require(area: str, check: Callable[[User, str], bool]) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not check(current_user, area):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


ROLE_LABELS = {
    Role.PROVIDER_ADMIN: "Provider Admin",
    Role.PROVIDER_LIMITED: "Provider Limited",
    Role.CARRIER_ADMIN: "Carrier Admin",
    Role.CARRIER_VIEWER: "Carrier Viewer",
}

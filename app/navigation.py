"""Sidebar navigation.

Items are listed once here. An item only appears when its endpoint is
registered (so the sidebar grows as features land) and, from the auth step on,
when the current user's role is allowed to see it.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app, g
from flask_login import current_user

from .permissions import can_view, is_provider


@dataclass(frozen=True)
class NavItem:
    label: str
    endpoint: str
    area: str
    provider_only: bool = False
    needs_tenant: bool = True


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(
        "Carrier clients", "dashboard.provider", "dashboard", provider_only=True, needs_tenant=False
    ),
    NavItem("Dashboard", "dashboard.carrier", "dashboard"),
    NavItem("Drivers", "drivers.index", "drivers"),
    NavItem("Fleet", "fleet.index", "fleet"),
    NavItem("Hours of Service", "hos.index", "hos"),
    NavItem("Training", "training.index", "training"),
    NavItem("Import", "imports.index", "imports"),
    NavItem("Integrations", "integrations.index", "integrations"),
    NavItem("Audit log", "audit.index", "audit", needs_tenant=False),
)


def visible_nav_items() -> list[NavItem]:
    """Nav items whose views exist in this build and that this user may see.

    Provider users see tenant pages only after picking a carrier in the switcher.
    """
    if not current_user.is_authenticated:
        return []
    registered = current_app.view_functions
    provider = is_provider(current_user)
    has_tenant = g.get("active_tenant") is not None
    return [
        item
        for item in NAV_ITEMS
        if item.endpoint in registered
        and can_view(current_user, item.area)
        and (provider or not item.provider_only)
        and (has_tenant or not item.needs_tenant)
    ]

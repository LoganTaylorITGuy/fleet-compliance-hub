"""Sidebar navigation.

Items are listed once here. An item only appears when its endpoint is
registered (so the sidebar grows as features land) and, from the auth step on,
when the current user's role is allowed to see it.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app


@dataclass(frozen=True)
class NavItem:
    label: str
    endpoint: str


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Dashboard", "main.index"),
    NavItem("Carrier clients", "dashboard.provider"),
    NavItem("Drivers", "drivers.index"),
    NavItem("Fleet", "fleet.index"),
    NavItem("Hours of Service", "hos.index"),
    NavItem("Training", "training.index"),
    NavItem("Import", "imports.index"),
    NavItem("Integrations", "integrations.index"),
    NavItem("Audit log", "audit.index"),
)


def visible_nav_items() -> list[NavItem]:
    """Return the nav items whose views exist in this build."""
    registered = current_app.view_functions
    return [item for item in NAV_ITEMS if item.endpoint in registered]

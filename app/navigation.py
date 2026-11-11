"""Navigation: the Menu overlay and the bottom search bar's page results.

Items are listed once here. An item only appears when its endpoint is
registered and the current user's role is allowed to see it.
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
    icon: str
    description: str = ""
    keywords: str = ""  # extra words that suggest this page while typing in search
    provider_only: bool = False
    needs_tenant: bool = True


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(
        "Carrier clients",
        "dashboard.provider",
        "dashboard",
        "carriers",
        "Every carrier, most urgent first",
        "clients companies tenants provider overview",
        provider_only=True,
        needs_tenant=False,
    ),
    NavItem(
        "Dashboard",
        "dashboard.carrier",
        "dashboard",
        "dashboard",
        "What needs action and what's due",
        "home overview status expiring overdue red yellow green",
    ),
    NavItem(
        "Drivers",
        "drivers.index",
        "drivers",
        "drivers",
        "Qualification files, tests and hours",
        "cdl medical card dq file mvr drug alcohol test students roster",
    ),
    NavItem(
        "Fleet",
        "fleet.index",
        "fleet",
        "fleet",
        "Units, inspections and maintenance",
        "trucks tractors trailers units dvir maintenance repairs shop registration inspection vin",
    ),
    NavItem(
        "Hours of Service",
        "hos.index",
        "hos",
        "hos",
        "Last 7 days from the ELD",
        "hos eld logs violations motive driving duty",
    ),
    NavItem(
        "Training",
        "training.index",
        "training",
        "training",
        "Academy progress and certifications",
        "academy students courses eldt hazmat certification",
    ),
    NavItem(
        "Import",
        "imports.index",
        "imports",
        "imports",
        "Bring in your spreadsheets",
        "upload excel csv spreadsheet xlsx templates mapping undo",
    ),
    NavItem(
        "Integrations",
        "integrations.index",
        "integrations",
        "integrations",
        "Motive connection and sync",
        "motive eld sync connect api",
    ),
    NavItem(
        "Audit log",
        "audit.index",
        "audit",
        "audit",
        "Who changed what, and when",
        "history changes log activity who",
        needs_tenant=False,
    ),
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

"""Helpers shared by the feature blueprints."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from flask import current_app, flash, g, redirect, url_for

from .models import Driver, Vehicle


def tenant_required(view: Callable) -> Callable:
    """Carrier pages need a tenant. Provider staff without one pick a carrier first."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("active_tenant") is None:
            flash("Choose a carrier first.", "warning")
            return redirect(url_for("dashboard.provider"))
        return view(*args, **kwargs)

    return wrapped


def link_for(obj) -> str | None:
    """Detail-page URL for a driver or unit, once those pages exist."""
    endpoints = current_app.view_functions
    if isinstance(obj, Driver) and "drivers.detail" in endpoints:
        return url_for("drivers.detail", driver_id=obj.id)
    if isinstance(obj, Vehicle) and "fleet.detail" in endpoints:
        return url_for("fleet.detail", vehicle_id=obj.id)
    return None


def display_name(obj) -> str:
    if isinstance(obj, Driver):
        return obj.full_name
    if isinstance(obj, Vehicle):
        return f"Unit {obj.unit_number}"
    return str(obj)

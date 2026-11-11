"""Quick search for the navigation overlay: drivers and units in the current carrier.

Runs in the request's tenant scope (app/tenancy.py), so results only ever come
from the carrier being viewed, and respects role permissions.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request, url_for
from flask_login import current_user
from sqlalchemy import or_, select

from .extensions import db
from .models import Driver, Vehicle
from .permissions import can_view

bp = Blueprint("search", __name__, url_prefix="/search")

MAX_RESULTS = 8


@bp.get("/")
def search():
    term = request.args.get("q", "").strip()[:60]
    if len(term) < 2 or g.get("active_tenant") is None:
        return jsonify(results=[])
    like = f"%{term}%"
    results = []
    if can_view(current_user, "drivers"):
        drivers = db.session.scalars(
            select(Driver)
            .where(
                or_(
                    Driver.first_name.ilike(like),
                    Driver.last_name.ilike(like),
                    (Driver.first_name + " " + Driver.last_name).ilike(like),
                    Driver.cdl_number.ilike(like),
                )
            )
            .order_by(Driver.last_name)
            .limit(MAX_RESULTS)
        )
        results += [
            {
                "kind": "Driver",
                "title": d.full_name,
                "detail": f"CDL {d.cdl_number}" + (" · student" if d.is_student else ""),
                "url": url_for("drivers.detail", driver_id=d.id),
            }
            for d in drivers
        ]
    if can_view(current_user, "fleet"):
        vehicles = db.session.scalars(
            select(Vehicle)
            .where(or_(Vehicle.unit_number.ilike(like), Vehicle.vin.ilike(like)))
            .order_by(Vehicle.unit_number)
            .limit(MAX_RESULTS)
        )
        results += [
            {
                "kind": "Unit",
                "title": f"Unit {v.unit_number}",
                "detail": f"{v.vehicle_type.capitalize()} · {v.year or ''} {v.make or ''}".strip(),
                "url": url_for("fleet.detail", vehicle_id=v.id),
            }
            for v in vehicles
        ]
    return jsonify(results=results[: MAX_RESULTS * 2])

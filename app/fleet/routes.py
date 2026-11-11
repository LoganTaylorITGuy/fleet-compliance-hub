from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..clock import today
from ..compliance import vehicle_status
from ..compliance.rules import annual_inspection_due, next_maintenance_due
from ..compliance.service import load_vehicles
from ..extensions import db
from ..forms import ActionForm, MaintenanceForm
from ..listing import LEVEL_CHOICES, level_filter, matches, search_term
from ..models import MaintenanceRecord, RepairStatus, Vehicle, VehicleType
from ..permissions import can_edit, require_edit, require_view
from ..tenancy import scoped_get_or_404
from ..views import tenant_required
from . import bp


@bp.get("/")
@require_view("fleet")
@tenant_required
def index():
    term, wanted = search_term(), level_filter()
    vtype = request.args.get("type", "")
    day = today()
    rows = []
    for vehicle in load_vehicles():
        status = vehicle_status(vehicle, day)
        if wanted is not None and status.level != wanted:
            continue
        if vtype in (VehicleType.TRACTOR, VehicleType.TRAILER) and vehicle.vehicle_type != vtype:
            continue
        if not matches(term, vehicle.unit_number, vehicle.vin, vehicle.plate, vehicle.make):
            continue
        rows.append(
            {
                "vehicle": vehicle,
                "status": status,
                "inspection_due": annual_inspection_due(vehicle.annual_inspection_on),
                "pm_due": next_maintenance_due(vehicle.maintenance),
                "in_shop": any(m.status == RepairStatus.OPEN for m in vehicle.maintenance),
            }
        )
    rows.sort(key=lambda r: (-r["status"].level, r["vehicle"].unit_number))
    return render_template(
        "fleet/index.html", rows=rows, term=term, vtype=vtype, level_choices=LEVEL_CHOICES
    )


@bp.get("/<int:vehicle_id>")
@require_view("fleet")
@tenant_required
def detail(vehicle_id: int):
    vehicle = scoped_get_or_404(Vehicle, vehicle_id)
    day = today()
    can_maintain = can_edit(current_user, "maintenance")
    return render_template(
        "fleet/detail.html",
        vehicle=vehicle,
        status=vehicle_status(vehicle, day),
        inspection_due=annual_inspection_due(vehicle.annual_inspection_on),
        pm_due=next_maintenance_due(vehicle.maintenance),
        maintenance=sorted(
            vehicle.maintenance,
            key=lambda m: (m.status != RepairStatus.OPEN, -m.performed_on.toordinal()),
        ),
        dvirs=sorted(vehicle.dvirs, key=lambda d: d.inspected_on, reverse=True),
        form=MaintenanceForm(performed_on=day) if can_maintain else None,
        action_form=ActionForm() if can_maintain else None,
    )


@bp.post("/<int:vehicle_id>/maintenance")
@require_edit("maintenance")
@tenant_required
def add_maintenance(vehicle_id: int):
    vehicle = scoped_get_or_404(Vehicle, vehicle_id)
    form = MaintenanceForm()
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            flash(f"{getattr(form, field).label.text}: {errors[0]}", "error")
        return redirect(url_for("fleet.detail", vehicle_id=vehicle.id))
    record = MaintenanceRecord(vehicle=vehicle, status=RepairStatus.COMPLETED)
    form.populate_obj(record)
    db.session.add(record)
    db.session.commit()
    flash(f"Maintenance added to unit {vehicle.unit_number}.", "success")
    return redirect(url_for("fleet.detail", vehicle_id=vehicle.id))


@bp.post("/maintenance/<int:record_id>/complete")
@require_edit("maintenance")
@tenant_required
def complete_repair(record_id: int):
    """Close an open shop repair. If it came from a DVIR, the defect is resolved too."""
    if not ActionForm().validate_on_submit():
        abort(400)
    record = scoped_get_or_404(MaintenanceRecord, record_id)
    if record.status != RepairStatus.OPEN:
        flash("That repair is already complete.", "warning")
        return redirect(url_for("fleet.detail", vehicle_id=record.vehicle_id))
    day = today()
    record.status = RepairStatus.COMPLETED
    record.performed_on = day
    if record.dvir is not None and not record.dvir.defect_resolved:
        record.dvir.defect_resolved = True
        record.dvir.resolved_on = day
    db.session.commit()
    flash("Repair marked complete and the DVIR defect resolved.", "success")
    return redirect(url_for("fleet.detail", vehicle_id=record.vehicle_id))

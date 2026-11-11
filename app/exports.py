"""Download any table as an Excel workbook, for reports and audits.

Exports run in the current tenant scope, so a carrier only ever exports its
own data. Text that a spreadsheet would treat as a formula is escaped.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta

import pandas as pd
from flask import Blueprint, abort, g, send_file
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .clock import today
from .compliance import driver_status, vehicle_status
from .compliance.rules import annual_inspection_due, next_maintenance_due
from .compliance.service import load_drivers, load_vehicles
from .extensions import db
from .formatting import localtime
from .models import AuditLog, Driver, HOSLog, TrainingRecord
from .permissions import can_view
from .views import tenant_required

bp = Blueprint("exports", __name__, url_prefix="/export")

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Stop spreadsheet formula injection: '=HYPERLINK(...)' is stored as text."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _top_issue(status) -> str:
    top = next(iter(status.sorted_findings()), None)
    return f"{top.label}: {top.message}" if top else ""


def drivers_rows() -> list[dict]:
    day = today()
    rows = []
    for d in load_drivers(day):
        status = driver_status(d, day)
        rows.append(
            {
                "Last name": d.last_name,
                "First name": d.first_name,
                "CDL number": d.cdl_number,
                "CDL state": d.cdl_state,
                "CDL class": d.cdl_class,
                "CDL expiration": d.cdl_expiration,
                "Medical card expiration": d.medical_card_expiration,
                "Hire date": d.hire_date,
                "Status": d.status,
                "Student": "Yes" if d.is_student else "No",
                "Compliance": status.level.text,
                "Top issue": _top_issue(status),
            }
        )
    return rows


def fleet_rows() -> list[dict]:
    day = today()
    return [
        {
            "Unit": v.unit_number,
            "Type": v.vehicle_type,
            "Year": v.year,
            "Make": v.make,
            "VIN": v.vin,
            "Plate": v.plate,
            "Plate state": v.plate_state,
            "Registration expiration": v.registration_expiration,
            "Last annual inspection": v.annual_inspection_on,
            "Annual inspection due": annual_inspection_due(v.annual_inspection_on),
            "Next PM due": next_maintenance_due(v.maintenance),
            "Compliance": (status := vehicle_status(v, day)).level.text,
            "Top issue": _top_issue(status),
        }
        for v in load_vehicles()
    ]


def hos_rows() -> list[dict]:
    since = today() - timedelta(days=30)
    logs = db.session.scalars(
        select(HOSLog)
        .options(selectinload(HOSLog.driver))
        .where(HOSLog.log_date >= since)
        .order_by(HOSLog.log_date.desc())
    ).all()
    return [
        {
            "Date": log.log_date,
            "Driver": log.driver.full_name,
            "CDL number": log.driver.cdl_number,
            "Driving hours": log.driving_hours,
            "On-duty hours": log.on_duty_hours,
            "Off-duty hours": log.off_duty_hours,
            "Violation": "Yes" if log.violation else "No",
            "Violation note": log.violation_note,
            "Source": log.source,
        }
        for log in logs
    ]


def training_rows() -> list[dict]:
    records = db.session.scalars(
        select(TrainingRecord)
        .options(selectinload(TrainingRecord.driver))
        .join(TrainingRecord.driver)
        .order_by(Driver.last_name, TrainingRecord.course_name)
    ).all()
    return [
        {
            "Driver": t.driver.full_name,
            "CDL number": t.driver.cdl_number,
            "Student": "Yes" if t.driver.is_student else "No",
            "Course": t.course_name,
            "Category": t.category,
            "Completed": t.completed_on,
            "Expires": t.expires_on,
        }
        for t in records
    ]


def audit_rows() -> list[dict]:
    entries = db.session.scalars(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.id.desc())
        .limit(5000)
    ).all()
    return [
        {
            "When (US Central)": localtime(e.created_at),
            "Who": e.user.name if e.user else "System",
            "Action": e.action,
            "Record type": e.table_name,
            "Record id": e.record_id,
            "Summary": e.summary,
            "Before": str(e.before) if e.before else "",
            "After": str(e.after) if e.after else "",
        }
        for e in entries
    ]


DATASETS = {
    "drivers": ("Drivers", "drivers", drivers_rows),
    "fleet": ("Fleet", "fleet", fleet_rows),
    "hos": ("Hours of service (30 days)", "hos", hos_rows),
    "training": ("Training", "training", training_rows),
    "audit": ("Audit log", "audit", audit_rows),
}


def build_workbook(sheet_name: str, rows: list[dict]) -> io.BytesIO:
    clean = [{k: safe_cell(v) for k, v in row.items()} for row in rows]
    frame = pd.DataFrame(clean or [{"": "No data"}])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        sheet = writer.sheets[sheet_name[:31]]
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max(len(str(c.value or "")) for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)
            for cell in column[1:]:
                if isinstance(cell.value, datetime | date):
                    cell.number_format = "yyyy-mm-dd"
    buffer.seek(0)
    return buffer


@bp.get("/<dataset>.xlsx")
@tenant_required
def download(dataset: str):
    if dataset not in DATASETS:
        abort(404)
    title, area, build = DATASETS[dataset]
    if not can_view(current_user, area):
        abort(403)
    buffer = build_workbook(title, build())
    slug = "".join(ch if ch.isalnum() else "-" for ch in g.active_tenant.name.lower()).strip("-")
    filename = f"{slug}_{dataset}_{today().isoformat()}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

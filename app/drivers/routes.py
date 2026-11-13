"""Driver list, driver file (CDL, medical card, tests, training), edits, and audit packet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from flask import flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select

from .. import audit
from ..clock import today
from ..compliance import Level, driver_status
from ..compliance.rules import date_finding
from ..compliance.service import load_drivers
from ..extensions import db
from ..forms import DriverEditForm
from ..listing import LEVEL_CHOICES, level_filter, matches, search_term
from ..models import Driver, DriverFileItem, FileItemType, HOSLog, utcnow
from ..permissions import can_edit, require_edit, require_view
from ..tenancy import scoped_get_or_404
from ..views import tenant_required
from . import bp

FILE_CHECKLIST = [
    (FileItemType.APPLICATION, "Employment application"),
    (FileItemType.MVR, "Motor vehicle record (MVR)"),
    (FileItemType.ROAD_TEST, "Road test"),
    (FileItemType.PREVIOUS_EMPLOYER_CHECK, "Previous employer check"),
    (FileItemType.ANNUAL_REVIEW, "Annual review"),
]


@dataclass(frozen=True)
class FileRow:
    """One line of the qualification file checklist, with its own status."""

    label: str
    item: DriverFileItem | None
    level: Level
    note: str


def file_rows(driver: Driver, day: date) -> list[FileRow]:
    """The checklist with a status per item, as the audit packet prints it.

    A missing item is red. A completed item uses the same due-date rule as the
    dashboards, so the packet and the rest of the app always agree.
    """
    files = {item.item_type: item for item in driver.file_items}
    rows = []
    for key, label in FILE_CHECKLIST:
        item = files.get(key)
        if item is None or item.completed_on is None:
            rows.append(FileRow(label, item, Level.RED, "Not on file"))
            continue
        finding = date_finding(item.due_on, day, category="file", label=label, verb="Due")
        if finding is None:
            rows.append(FileRow(label, item, Level.GREEN, "On file"))
        else:
            rows.append(FileRow(label, item, finding.level, finding.message))
    return rows


def _driver_file(driver: Driver, day: date) -> dict:
    """Everything the driver page and the audit packet both show."""
    # Rules need the last 7 days of HOS; the pages show the same window.
    loaded = load_drivers(day, driver_ids=[driver.id])
    # Terminated drivers aren't in the evaluated set but still have a page.
    status = driver_status(loaded[0] if loaded else driver, day)
    files = {item.item_type: item for item in driver.file_items}
    hours = db.session.scalars(
        select(HOSLog)
        .where(HOSLog.driver_id == driver.id, HOSLog.log_date >= day - timedelta(days=7))
        .order_by(HOSLog.log_date.desc())
    ).all()
    return {
        "driver": driver,
        "status": status,
        "checklist": [(key, label, files.get(key)) for key, label in FILE_CHECKLIST],
        "tests": sorted(driver.tests, key=lambda t: t.tested_on, reverse=True),
        "trainings": sorted(driver.trainings, key=lambda t: t.expires_on or t.completed_on or day),
        "hours": hours,
        "Level": Level,
    }


@bp.get("/")
@require_view("drivers")
@tenant_required
def index():
    term, wanted = search_term(), level_filter()
    day = today()
    rows = []
    for driver in load_drivers(day):
        status = driver_status(driver, day)
        if wanted is not None and status.level != wanted:
            continue
        if not matches(term, driver.full_name, driver.cdl_number):
            continue
        rows.append((driver, status))
    rows.sort(key=lambda r: (-r[1].level, r[0].last_name))
    return render_template("drivers/index.html", rows=rows, term=term, level_choices=LEVEL_CHOICES)


@bp.get("/<int:driver_id>")
@require_view("drivers")
@tenant_required
def detail(driver_id: int):
    driver = scoped_get_or_404(Driver, driver_id)
    form = DriverEditForm(obj=driver) if can_edit(current_user, "drivers") else None
    return render_template("drivers/detail.html", form=form, **_driver_file(driver, today()))


@bp.get("/<int:driver_id>/packet")
@require_view("drivers")
@tenant_required
def packet(driver_id: int):
    """A printable audit packet for one driver: status, file, tests, training, hours.

    Anyone who can view the driver can generate one. Each packet is logged, and
    the audit entry's id is printed on it, so a packet in an auditor's hands
    can be traced to who pulled it and when (ADR 0011).
    """
    driver = scoped_get_or_404(Driver, driver_id)
    day = today()
    # Gather the file first, so the packet shows the record as it stood when logged.
    context = _driver_file(driver, day) | {"file_rows": file_rows(driver, day)}
    entry = audit.record(
        "packet",
        f"Generated the audit packet for {driver.full_name}",
        table_name=Driver.__tablename__,
        record_id=driver.id,
    )
    db.session.flush()
    reference, generated_at = entry.id, utcnow()
    db.session.commit()
    return render_template(
        "drivers/packet.html", reference=reference, generated_at=generated_at, **context
    )


@bp.post("/<int:driver_id>/edit")
@require_edit("drivers")
@tenant_required
def edit(driver_id: int):
    driver = scoped_get_or_404(Driver, driver_id)
    form = DriverEditForm()
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            flash(f"{getattr(form, field).label.text}: {errors[0]}", "error")
        return redirect(url_for("drivers.detail", driver_id=driver.id))
    form.populate_obj(driver)
    db.session.commit()  # the audit hook records before/after
    flash(f"Saved changes to {driver.full_name}.", "success")
    return redirect(url_for("drivers.detail", driver_id=driver.id))

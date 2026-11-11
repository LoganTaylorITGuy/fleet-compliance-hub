from __future__ import annotations

from datetime import timedelta

from flask import flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select

from ..clock import today
from ..compliance import Level, driver_status
from ..compliance.service import load_drivers
from ..extensions import db
from ..forms import DriverEditForm
from ..listing import LEVEL_CHOICES, level_filter, matches, search_term
from ..models import Driver, FileItemType, HOSLog
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
    day = today()
    # Rules need the last 7 days of HOS; the page shows the same window.
    loaded = load_drivers(day, driver_ids=[driver.id])
    # Terminated drivers aren't in the evaluated set but still have a page.
    status = driver_status(loaded[0] if loaded else driver, day)
    files = {item.item_type: item for item in driver.file_items}
    hours = db.session.scalars(
        select(HOSLog)
        .where(HOSLog.driver_id == driver.id, HOSLog.log_date >= day - timedelta(days=7))
        .order_by(HOSLog.log_date.desc())
    ).all()
    form = DriverEditForm(obj=driver) if can_edit(current_user, "drivers") else None
    return render_template(
        "drivers/detail.html",
        driver=driver,
        status=status,
        checklist=[(key, label, files.get(key)) for key, label in FILE_CHECKLIST],
        tests=sorted(driver.tests, key=lambda t: t.tested_on, reverse=True),
        trainings=sorted(driver.trainings, key=lambda t: t.expires_on or t.completed_on or day),
        hours=hours,
        form=form,
        Level=Level,
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

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..clock import today
from ..compliance import Level
from ..compliance.rules import date_finding
from ..extensions import db
from ..forms import ActionForm
from ..models import Driver, TrainingCategory, TrainingRecord
from ..permissions import can_edit, require_edit, require_view
from ..tenancy import scoped_get_or_404
from ..views import tenant_required
from . import bp


@bp.get("/")
@require_view("training")
@tenant_required
def index():
    """Academy students' progress, plus every driver's expiring certifications."""
    day = today()
    show = request.args.get("show", "")
    drivers = db.session.scalars(
        select(Driver)
        .options(selectinload(Driver.trainings))
        .order_by(Driver.last_name, Driver.first_name)
    ).all()

    students = []
    for d in (d for d in drivers if d.is_student):
        courses = sorted(
            (t for t in d.trainings if t.category == TrainingCategory.ACADEMY), key=lambda t: t.id
        )
        done = sum(1 for t in courses if t.completed_on)
        students.append({"driver": d, "courses": courses, "done": done, "total": len(courses)})

    certs = []
    for d in drivers:
        for t in d.trainings:
            if t.category == TrainingCategory.ACADEMY:
                continue
            finding = date_finding(t.expires_on, day, category="training", label=t.course_name)
            level = finding.level if finding else Level.GREEN
            if show == "upcoming" and level == Level.GREEN:
                continue
            certs.append({"driver": d, "training": t, "level": level, "finding": finding})
    certs.sort(key=lambda c: (-c["level"], c["training"].expires_on or day))
    return render_template(
        "training/index.html",
        students=students,
        certs=certs,
        show=show,
        action_form=ActionForm() if can_edit(current_user, "training") else None,
    )


@bp.post("/<int:training_id>/complete")
@require_edit("training")
@tenant_required
def complete(training_id: int):
    if not ActionForm().validate_on_submit():
        abort(400)
    record = scoped_get_or_404(TrainingRecord, training_id)
    if record.completed_on:
        flash("That course is already complete.", "warning")
    else:
        record.completed_on = today()
        db.session.commit()
        flash(f"{record.course_name} marked complete for {record.driver.full_name}.", "success")
    return redirect(url_for("training.index"))

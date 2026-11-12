"""Hours of service: a per-driver grid of daily logs with violations flagged."""

from __future__ import annotations

from datetime import timedelta

from flask import render_template, request
from sqlalchemy import select

from ..clock import today
from ..extensions import db
from ..models import Driver, HOSLog, IntegrationConnection
from ..permissions import require_view
from ..views import tenant_required
from . import bp

DAYS_SHOWN = 7


@bp.get("/")
@require_view("hos")
@tenant_required
def index():
    """Last 7 days of hours for every driver, as synced from Motive (mock)."""
    day = today()
    days = [day - timedelta(days=n) for n in range(DAYS_SHOWN, 0, -1)]
    violations_only = request.args.get("violations") == "1"
    logs = db.session.scalars(
        select(HOSLog).where(HOSLog.log_date >= days[0], HOSLog.log_date <= days[-1])
    ).all()
    by_driver: dict[int, dict] = {}
    for log in logs:
        by_driver.setdefault(log.driver_id, {})[log.log_date] = log
    drivers = db.session.scalars(
        select(Driver)
        .where(Driver.id.in_(by_driver.keys()))
        .order_by(Driver.last_name, Driver.first_name)
    ).all()
    rows = []
    for driver in drivers:
        cells = by_driver.get(driver.id, {})
        violations = [log for log in cells.values() if log.violation]
        if violations_only and not violations:
            continue
        rows.append(
            {
                "driver": driver,
                "cells": [cells.get(d) for d in days],
                "violations": violations,
                "driving_total": sum(log.driving_hours for log in cells.values()),
            }
        )
    rows.sort(key=lambda r: (not r["violations"], r["driver"].last_name))
    connection = db.session.scalars(
        select(IntegrationConnection).where(IntegrationConnection.service == "motive")
    ).first()
    return render_template(
        "hos/index.html",
        rows=rows,
        days=days,
        violations_only=violations_only,
        violation_count=sum(len(r["violations"]) for r in rows),
        last_synced=connection.last_synced_at if connection else None,
    )

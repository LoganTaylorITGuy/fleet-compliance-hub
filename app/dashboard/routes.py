"""Dashboards: the provider's ranked list of carriers, and one carrier's
"needs action now" view."""

from __future__ import annotations

from flask import abort, g, render_template
from flask_login import current_user

from ..clock import today
from ..compliance import TenantSummary, evaluate
from ..compliance.service import Counts, provider_carrier_summaries
from ..permissions import is_provider, require_view
from ..views import tenant_required
from . import bp


@bp.get("/provider")
@require_view("dashboard")
def provider():
    """Every carrier client, most urgent first."""
    if not is_provider(current_user):
        abort(403)
    rows = provider_carrier_summaries(current_user.provider_id, today())
    totals = Counts()
    for row in rows:
        c = row.summary.counts
        totals.red += c.red
        totals.yellow += c.yellow
        totals.green += c.green
    return render_template(
        "dashboard/provider.html",
        rows=rows,
        totals=totals,
        driver_total=sum(len(r.summary.drivers) for r in rows),
        unit_total=sum(len(r.summary.vehicles) for r in rows),
    )


@bp.get("/")
@require_view("dashboard")
@tenant_required
def carrier():
    """One carrier: counts, what needs action now, and what's expiring in 30 days."""
    tenant = g.active_tenant
    summary = evaluate(today()).get(tenant.id, TenantSummary(tenant.id))
    return render_template("dashboard/carrier.html", tenant=tenant, summary=summary)

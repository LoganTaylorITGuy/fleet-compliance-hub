from __future__ import annotations

from dataclasses import dataclass

from flask import abort, g, render_template
from flask_login import current_user
from sqlalchemy import select

from ..clock import today
from ..compliance import TenantSummary, evaluate
from ..compliance.service import Counts
from ..extensions import db
from ..models import Tenant
from ..permissions import is_provider, require_view
from ..tenancy import all_tenants
from ..views import tenant_required
from . import bp


@dataclass
class TenantRow:
    tenant: Tenant
    summary: TenantSummary


@bp.get("/provider")
@require_view("dashboard")
def provider():
    """Every carrier client, most urgent first."""
    if not is_provider(current_user):
        abort(403)
    tenants = db.session.scalars(
        select(Tenant).where(Tenant.provider_id == current_user.provider_id)
    ).all()
    # Provider staff read across their own carriers; tenant rows are matched
    # back to this provider's tenant list, so another provider's data never shows.
    with all_tenants():
        summaries = evaluate(today())
    rows = [TenantRow(t, summaries.get(t.id, TenantSummary(t.id))) for t in tenants]
    rows.sort(key=lambda r: (*r.summary.urgency, r.tenant.name))
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

"""Home (the launcher every user lands on), favicon, and the /healthz check."""

from flask import g, jsonify, redirect, render_template, url_for
from flask_login import current_user

from .. import clock
from ..compliance import TenantSummary, evaluate
from ..compliance.service import CarrierSummary, provider_carrier_summaries
from ..navigation import visible_nav_items
from ..permissions import can_view, is_provider
from . import bp
from .greetings import first_name, greet


@bp.get("/")
def index():
    """Home: a greeting, where things stand, and a tile for every page this user can open."""
    moment = clock.now()
    tenant = g.get("active_tenant")
    summary = carriers = None
    if tenant is not None:
        summary = evaluate(moment.date()).get(tenant.id, TenantSummary(tenant.id))
    elif is_provider(current_user) and can_view(current_user, "dashboard"):
        carriers = provider_carrier_summaries(current_user.provider_id, moment.date())
    tiles = [item for item in visible_nav_items() if item.endpoint != "main.index"]
    return render_template(
        "main/launcher.html",
        greeting=greet(first_name(current_user.name), moment, seed=current_user.id),
        moment=moment,
        tenant=tenant,
        summary=summary,
        carriers=carriers,
        tiles=tiles,
        badges=_action_badges(summary, carriers),
    )


def _action_badges(
    summary: TenantSummary | None, carriers: list[CarrierSummary] | None
) -> dict[str, int]:
    """Red ("needs action") counts to show on tiles, by endpoint; zeros are left out."""
    counts = {}
    if summary is not None:
        counts = {
            "dashboard.carrier": summary.counts.red,
            "drivers.index": summary.driver_counts.red,
            "fleet.index": summary.vehicle_counts.red,
        }
    elif carriers is not None:
        counts = {"dashboard.provider": sum(c.summary.counts.red for c in carriers)}
    return {endpoint: n for endpoint, n in counts.items() if n}


@bp.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="brand/favicon-32.png"), code=301)


@bp.get("/healthz")
def healthz():
    """Liveness check for staging and production hosting."""
    return jsonify(status="ok")

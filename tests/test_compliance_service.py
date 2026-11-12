"""Compliance service against seeded data: scoping, status mix and urgency order."""

from datetime import date

from sqlalchemy import select

from app.compliance import Level, evaluate
from app.extensions import db
from app.models import Tenant
from app.seed import seed_demo
from app.tenancy import all_tenants, tenant_scope

TODAY = date(2026, 11, 17)


def _tenant_ids():
    return {t.name: t.id for t in db.session.scalars(select(Tenant))}


def test_evaluate_in_tenant_scope_returns_only_that_tenant(app):
    seed_demo("P", today=TODAY)
    ids = _tenant_ids()
    with tenant_scope(ids["Red Draw Hauling Co."]):
        summaries = evaluate(TODAY)
    assert list(summaries) == [ids["Red Draw Hauling Co."]]
    summary = summaries[ids["Red Draw Hauling Co."]]
    assert len(summary.drivers) == 8
    assert len(summary.vehicles) == 14


def test_seeded_mix_has_reds_yellows_and_mostly_greens(app):
    seed_demo("P", today=TODAY)
    with all_tenants():
        summaries = evaluate(TODAY)
    assert len(summaries) == 4
    for summary in summaries.values():
        counts = summary.counts
        assert counts.red >= 1, summary.tenant_id
        assert counts.yellow >= 1, summary.tenant_id
        assert counts.green > counts.total / 2, summary.tenant_id


def test_planted_demo_items_show_up(app):
    seed_demo("P", today=TODAY)
    with tenant_scope(_tenant_ids()["Red Draw Hauling Co."]):
        summary = next(iter(evaluate(TODAY).values()))
    categories = {f.category for _, f in summary.needs_action}
    assert {"hos", "dvir"} <= categories
    expiring = [(who, f) for who, f in summary.expiring_soon if f.category == "medical"]
    assert any("in 12 days" in f.message for _, f in expiring)
    dues = [f.due for _, f in summary.expiring_soon]
    assert dues == sorted(dues)


def test_urgency_orders_most_reds_first(app):
    seed_demo("P", today=TODAY)
    with all_tenants():
        ranked = sorted(evaluate(TODAY).values(), key=lambda s: s.urgency)
    reds = [s.counts.red for s in ranked]
    assert reds == sorted(reds, reverse=True)


def test_counts_split_drivers_and_vehicles(app):
    seed_demo("P", today=TODAY)
    with all_tenants():
        summary = next(iter(evaluate(TODAY).values()))
    total = summary.driver_counts.total + summary.vehicle_counts.total
    assert total == summary.counts.total == len(summary.drivers) + len(summary.vehicles)
    assert Level.RED.text == "Action needed"

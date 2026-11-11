"""Tenant isolation: carrier A must never read or change carrier B's data.

These tests run as their own CI job. Every tenant-scoped model is covered
automatically via TENANT_SCOPED_MODELS, so a new model can't skip them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.models import TENANT_SCOPED_MODELS, AuditLog, Driver, DrugAlcoholTest, Vehicle
from app.tenancy import (
    TenantScope,
    TenantScoped,
    TenantViolation,
    all_tenants,
    scoped_get_or_404,
    set_request_scope,
    tenant_scope,
)

from .factories import make_provider, make_tenant, populate_tenant

pytestmark = pytest.mark.isolation

MODEL_IDS = [m.__name__ for m in TENANT_SCOPED_MODELS]


@pytest.fixture
def two_tenants(app):
    provider = make_provider()
    a = make_tenant(provider, "Carrier A")
    b = make_tenant(provider, "Carrier B")
    ids = {"a": a.id, "b": b.id}
    with all_tenants():
        ids["rows_a"] = {name: row.id for name, row in populate_tenant(a, "A").items()}
        ids["rows_b"] = {name: row.id for name, row in populate_tenant(b, "B").items()}
    db.session.expunge_all()  # start every test with an empty identity map
    return ids


def test_every_scoped_model_is_registered():
    """A TenantScoped model missing from TENANT_SCOPED_MODELS would skip these tests."""
    scoped = {m.class_ for m in db.Model.registry.mappers if issubclass(m.class_, TenantScoped)}
    assert scoped == set(TENANT_SCOPED_MODELS)


@pytest.mark.parametrize("model", TENANT_SCOPED_MODELS, ids=MODEL_IDS)
def test_select_only_returns_current_tenant(two_tenants, model):
    with tenant_scope(two_tenants["a"]):
        rows = db.session.scalars(select(model)).all()
    assert rows, f"tenant A should see its own {model.__name__}"
    assert {r.tenant_id for r in rows} == {two_tenants["a"]}


@pytest.mark.parametrize("model", TENANT_SCOPED_MODELS, ids=MODEL_IDS)
def test_guessing_another_tenants_id_returns_404(two_tenants, model):
    other_id = two_tenants["rows_b"][model.__name__]
    with tenant_scope(two_tenants["a"]), pytest.raises(NotFound):
        scoped_get_or_404(model, other_id)


@pytest.mark.parametrize("model", TENANT_SCOPED_MODELS, ids=MODEL_IDS)
def test_no_scope_sees_nothing(two_tenants, model):
    """Fail closed: code that forgets to set a scope gets an empty result."""
    assert db.session.scalars(select(model)).all() == []


def test_request_scope_applies_without_context_manager(app, two_tenants):
    with app.test_request_context():
        set_request_scope(TenantScope(tenant_id=two_tenants["b"]))
        names = db.session.scalars(select(Driver.last_name)).all()
    assert names == ["BLast"]


def test_all_tenants_scope_sees_everything(two_tenants):
    with all_tenants():
        count = db.session.scalar(select(func.count()).select_from(Driver))
    assert count == 2


def test_aggregates_are_filtered(two_tenants):
    with tenant_scope(two_tenants["a"]):
        count = db.session.scalar(select(func.count(Driver.id)))
    assert count == 1


def test_relationship_lazy_loads_are_filtered(two_tenants):
    with tenant_scope(two_tenants["a"]):
        driver = db.session.scalars(select(Driver)).one()
        assert [t.tenant_id for t in driver.tests] == [two_tenants["a"]]
        assert all(log.tenant_id == two_tenants["a"] for log in driver.hos_logs)


def test_joins_cannot_reach_other_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        rows = db.session.execute(
            select(Driver.last_name, DrugAlcoholTest.result).join(DrugAlcoholTest)
        ).all()
    assert [r.last_name for r in rows] == ["ALast"]


def test_bulk_update_only_touches_current_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        db.session.execute(update(Driver).values(status="on_leave"))
        db.session.commit()
    with all_tenants():
        statuses = dict(db.session.execute(select(Driver.tenant_id, Driver.status)).all())
    assert statuses == {two_tenants["a"]: "on_leave", two_tenants["b"]: "active"}


def test_bulk_delete_only_touches_current_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        db.session.execute(delete(Vehicle))
        db.session.commit()
    with all_tenants():
        remaining = db.session.scalars(select(Vehicle.tenant_id)).all()
    assert remaining == [two_tenants["b"]]


def test_new_rows_are_stamped_with_current_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        driver = Driver(first_name="New", last_name="Hire", cdl_number="NEW-1")
        db.session.add(driver)
        db.session.commit()
        assert driver.tenant_id == two_tenants["a"]


def test_cannot_create_row_in_another_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        db.session.add(
            Driver(tenant_id=two_tenants["b"], first_name="X", last_name="Y", cdl_number="X-1")
        )
        with pytest.raises(TenantViolation):
            db.session.flush()
        db.session.rollback()


def test_cannot_move_row_to_another_tenant(two_tenants):
    with tenant_scope(two_tenants["a"]):
        driver = db.session.scalars(select(Driver)).one()
        driver.tenant_id = two_tenants["b"]
        with pytest.raises(TenantViolation):
            db.session.flush()
        db.session.rollback()


def test_cannot_link_child_to_other_tenants_parent(two_tenants):
    with all_tenants():
        driver_b = db.session.scalars(
            select(Driver).where(Driver.tenant_id == two_tenants["b"])
        ).one()
        db.session.add(
            DrugAlcoholTest(
                tenant_id=two_tenants["a"],
                driver=driver_b,
                test_type="random",
                tested_on=driver_b.hire_date or driver_b.cdl_expiration,
                result="negative",
            )
        )
        with pytest.raises(TenantViolation):
            db.session.flush()
        db.session.rollback()


def test_writes_without_scope_are_refused(two_tenants):
    db.session.add(
        Driver(tenant_id=two_tenants["a"], first_name="X", last_name="Y", cdl_number="Z")
    )
    with pytest.raises(TenantViolation):
        db.session.flush()
    db.session.rollback()


def test_all_tenants_scope_requires_explicit_tenant(two_tenants):
    with all_tenants():
        db.session.add(Driver(first_name="X", last_name="Y", cdl_number="Z"))
        with pytest.raises(TenantViolation):
            db.session.flush()
        db.session.rollback()


def test_provider_level_audit_rows_hidden_from_carriers(two_tenants):
    with all_tenants():
        db.session.add(AuditLog(tenant_id=None, action="provider_setting"))
        db.session.commit()
    with tenant_scope(two_tenants["a"]):
        actions = db.session.scalars(select(AuditLog.action)).all()
    assert "provider_setting" not in actions


def test_identity_map_cannot_leak_other_tenant(two_tenants):
    """Even if tenant B's driver is already loaded in the session, A gets a 404."""
    with all_tenants():
        driver_b = db.session.scalars(
            select(Driver).where(Driver.tenant_id == two_tenants["b"])
        ).one()
    with tenant_scope(two_tenants["a"]), pytest.raises(NotFound):
        scoped_get_or_404(Driver, driver_b.id)


def test_app_code_never_uses_unscoped_primary_key_lookups():
    """session.get() and db.get_or_404() read the identity map and can skip the filter."""
    pattern = re.compile(r"\b(session\.get|get_or_404|query\.get)\(")
    offenders = []
    for path in Path("app").rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line) and "scoped_get_or_404" not in line:
                offenders.append(f"{path}:{number}: {line.strip()}")
    assert offenders == [], "Use scoped_get_or_404 instead:\n" + "\n".join(offenders)

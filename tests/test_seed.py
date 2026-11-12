"""Demo seed: sizes, logins, planted demo records, tenant consistency, determinism."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.auth.services import DEMO_PERSONAS, authenticate
from app.extensions import db
from app.models import (
    DVIR,
    Driver,
    DrugAlcoholTest,
    HOSLog,
    MaintenanceRecord,
    RepairStatus,
    Role,
    Tenant,
    User,
    Vehicle,
)
from app.seed import DEFAULT_PASSWORD, has_data, reset_all, seed_demo
from app.tenancy import all_tenants

TODAY = date(2026, 11, 17)


@pytest.fixture
def seeded(app):
    summary = seed_demo("Test Provider", today=TODAY)
    return summary


def _scalar(stmt):
    with all_tenants():
        return db.session.scalar(stmt)


def test_tenant_sizes(seeded):
    assert {k: v["drivers"] for k, v in seeded.items()} == {
        "small": 3,
        "medium": 8,
        "large": 15,
        "academy": 8,  # 2 instructors + 6 students
    }
    assert _scalar(select(func.count()).select_from(Tenant)) == 4


def test_every_demo_persona_can_log_in(seeded):
    for email, *_ in DEMO_PERSONAS.values():
        assert authenticate(email, DEFAULT_PASSWORD) is not None, email


def test_role_coverage(seeded):
    roles = set(db.session.scalars(select(User.role)))
    assert roles == {r.value for r in Role}


def test_planted_expiring_medical_card(seeded):
    medium = _scalar(select(Tenant.id).where(Tenant.name == "Red Draw Hauling Co."))
    expiring = _scalar(
        select(func.count())
        .select_from(Driver)
        .where(Driver.tenant_id == medium, Driver.medical_card_expiration == TODAY + timedelta(12))
    )
    assert expiring == 1


def test_planted_recent_hos_violation(seeded):
    medium = _scalar(select(Tenant.id).where(Tenant.name == "Red Draw Hauling Co."))
    recent = _scalar(
        select(func.count())
        .select_from(HOSLog)
        .where(
            HOSLog.tenant_id == medium,
            HOSLog.violation.is_(True),
            HOSLog.log_date >= TODAY - timedelta(days=7),
        )
    )
    assert recent >= 1


def test_open_dvir_defect_links_to_open_shop_repair(seeded):
    with all_tenants():
        dvir = db.session.scalars(
            select(DVIR).where(DVIR.defect_found.is_(True), DVIR.defect_resolved.is_(False))
        ).one()
        assert dvir.vehicle.vehicle_type == "trailer"
        [repair] = dvir.repairs
        assert repair.status == RepairStatus.OPEN
        assert repair.shop_name == "In-house trailer shop"


def test_failed_test_exists(seeded):
    assert (
        _scalar(
            select(func.count())
            .select_from(DrugAlcoholTest)
            .where(DrugAlcoholTest.result == "positive")
        )
        == 1
    )


def test_thirty_days_of_hos_for_working_drivers(seeded):
    days = _scalar(select(func.count(func.distinct(HOSLog.log_date))))
    assert days == 30
    assert _scalar(select(func.max(HOSLog.log_date))) == TODAY - timedelta(days=1)


def test_children_share_parent_tenant(seeded):
    mismatched = _scalar(
        select(func.count())
        .select_from(MaintenanceRecord)
        .join(MaintenanceRecord.vehicle)
        .where(MaintenanceRecord.tenant_id != Vehicle.tenant_id)
    )
    assert mismatched == 0


def test_seed_is_deterministic(app):
    seed_demo("P", today=TODAY)
    first = sorted(db.session.scalars(select(User.email)))
    with all_tenants():
        names_1 = sorted(db.session.scalars(select(Driver.last_name)))
    reset_all()
    assert not has_data()
    seed_demo("P", today=TODAY)
    with all_tenants():
        names_2 = sorted(db.session.scalars(select(Driver.last_name)))
    assert names_1 == names_2
    assert first == sorted(db.session.scalars(select(User.email)))


def test_academy_name_override(app, monkeypatch):
    monkeypatch.setenv("DEMO_ACADEMY_NAME", "Example Driving School")
    seed_demo("P", today=TODAY)
    assert (
        db.session.scalar(select(Tenant.kind).where(Tenant.name == "Example Driving School"))
        == "academy"
    )

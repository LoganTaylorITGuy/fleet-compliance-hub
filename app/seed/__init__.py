"""Demo data: one provider, three fictional carriers and an academy fleet.

Everything is fake: company names, people, DOT/MC/CDL numbers and VINs. Dates
are relative to the day you seed, so statuses stay realistic: re-seed the day
before a demo.

The random generator is seeded, so every run produces the same people and
trucks. A few records are planted on purpose for the demo script
(see scenario.py):

* Red Draw Hauling (the carrier the demo Carrier Admin/Viewer log in to) has a
  driver whose medical card expires in 12 days, and a driver with an hours of
  service violation 2 days ago.
* One of its trailers has an open DVIR defect linked to an open repair in the
  provider's in-house trailer shop.

Modules:

* plans.py: the shape of the data set (tenants, sizes, courses).
* generator.py: the seeded random bulk data.
* scenario.py: the hand-placed demo records and the demo logins.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time

from sqlalchemy import delete, select

from ..audit import audit_suppressed, record
from ..extensions import db
from ..models import (
    DVIR,
    AuditLog,
    Driver,
    DriverFileItem,
    DrugAlcoholTest,
    HOSLog,
    ImportRun,
    ImportTemplate,
    IntegrationConnection,
    MaintenanceRecord,
    Provider,
    Tenant,
    TrainingRecord,
    User,
    Vehicle,
)
from ..tenancy import all_tenants
from .generator import Seeder
from .scenario import build_users, plant_demo_moments

DEFAULT_PASSWORD = "fleet-demo-2026"  # noqa: S105 - documented demo password, override with SEED_PASSWORD


# Delete order: children before parents.
_TABLES_IN_DELETE_ORDER = (
    AuditLog,
    ImportRun,
    ImportTemplate,
    IntegrationConnection,
    MaintenanceRecord,
    DVIR,
    HOSLog,
    TrainingRecord,
    DrugAlcoholTest,
    DriverFileItem,
    Vehicle,
    Driver,
    User,
    Tenant,
    Provider,
)


def has_data() -> bool:
    return db.session.scalars(select(Provider.id)).first() is not None


def reset_all() -> None:
    """Delete every row in every table. Local and demo databases only."""
    with all_tenants():
        for model in _TABLES_IN_DELETE_ORDER:
            db.session.execute(delete(model))
        db.session.commit()


def seed_demo(
    provider_name: str, *, today: date | None = None, password: str | None = None
) -> dict:
    """Load the demo data set. Returns a small summary for the CLI to print."""
    today = today or date.today()
    password = password or os.environ.get("SEED_PASSWORD", "").strip() or DEFAULT_PASSWORD
    with all_tenants(), audit_suppressed():
        provider, tenants = Seeder(today).run(provider_name)
        plant_demo_moments(tenants, today)
        build_users(provider, tenants, password)
        db.session.flush()
        for tenant in tenants.values():
            record("seed", f"Loaded demo data for {tenant.name}", tenant_id=tenant.id)
        record("seed", "Loaded demo data set")
        stamp = datetime.combine(today, time(6, 0), tzinfo=UTC)
        for connection in db.session.scalars(select(IntegrationConnection)):
            connection.last_synced_at = stamp
        db.session.commit()
        counts = {
            plan_key: {
                "name": t.name,
                "drivers": db.session.query(Driver).filter_by(tenant_id=t.id).count(),
                "vehicles": db.session.query(Vehicle).filter_by(tenant_id=t.id).count(),
            }
            for plan_key, t in tenants.items()
        }
    return counts

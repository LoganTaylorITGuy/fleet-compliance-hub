"""Hand-placed records that the 10-minute demo walkthrough relies on.

generator.py makes realistic but random data; this module makes sure each
step of the README walkthrough has exactly the record it needs to show.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from ..auth.services import hash_password
from ..extensions import db
from ..models import (
    DVIR,
    Driver,
    DriverStatus,
    DrugAlcoholTest,
    DrugTestResult,
    DrugTestType,
    HOSLog,
    MaintenanceRecord,
    Provider,
    RepairStatus,
    Role,
    ShopType,
    Tenant,
    User,
    Vehicle,
    VehicleType,
)
from .plans import TRAILER_SHOP


def plant_demo_moments(tenants: dict[str, Tenant], today: date) -> None:
    """Make sure every step of the demo script has something to show."""

    def days(n: int) -> date:
        return today + timedelta(days=n)

    db.session.flush()
    medium = tenants["medium"]
    drivers = db.session.scalars(
        select(Driver).where(Driver.tenant_id == medium.id).order_by(Driver.id)
    ).all()

    # 1. Medical card expiring in 12 days, otherwise a clean file.
    featured = drivers[1]
    featured.medical_card_expiration = days(12)
    featured.cdl_expiration = days(900)
    for training in featured.trainings:
        training.expires_on = days(400)
    for item in featured.file_items:
        if item.due_on:
            item.completed_on, item.due_on = days(-60), days(305)

    # 2. HOS violation two days ago (red: within the last 7 days).
    log = db.session.scalars(
        select(HOSLog).where(HOSLog.driver_id == drivers[2].id, HOSLog.log_date == days(-2))
    ).one()
    log.driving_hours, log.on_duty_hours, log.off_duty_hours = 11.75, 14.5, 9.5
    log.violation, log.violation_note = True, "11-hour driving limit exceeded"

    # 3. Trailer with an open DVIR defect, in the in-house trailer shop now.
    trailer = db.session.scalars(
        select(Vehicle)
        .where(Vehicle.tenant_id == medium.id, Vehicle.vehicle_type == VehicleType.TRAILER)
        .order_by(Vehicle.id)
    ).first()
    dvir = DVIR(
        tenant_id=medium.id,
        vehicle_id=trailer.id,
        driver_id=drivers[0].id,
        inspected_on=days(-1),
        defects="Air leak at gladhand, brake chamber on axle 2 not holding pressure",
        defect_found=True,
        defect_resolved=False,
        external_id="mock-dvir-demo-open",
    )
    db.session.add(dvir)
    db.session.flush()
    db.session.add(
        MaintenanceRecord(
            tenant_id=medium.id,
            vehicle_id=trailer.id,
            dvir_id=dvir.id,
            performed_on=today,
            work_done="Replace gladhand seal and axle 2 brake chamber (from DVIR)",
            shop_type=ShopType.IN_HOUSE,
            shop_name=TRAILER_SHOP,
            status=RepairStatus.OPEN,
        )
    )

    # 4. One failed random test in the large carrier (red).
    large_driver = db.session.scalars(
        select(Driver).where(Driver.tenant_id == tenants["large"].id).order_by(Driver.id)
    ).all()[5]
    db.session.add(
        DrugAlcoholTest(
            tenant_id=tenants["large"].id,
            driver_id=large_driver.id,
            test_type=DrugTestType.RANDOM,
            tested_on=days(-4),
            result=DrugTestResult.POSITIVE,
        )
    )
    large_driver.status = DriverStatus.ON_LEAVE


def build_users(provider: Provider, tenants: dict[str, Tenant], password: str) -> None:
    """One login per role; README lists them for the demo."""
    password_hash = hash_password(password)

    def user(email, name, role, *, tenant=None, permissions=""):
        db.session.add(
            User(
                email=email,
                name=name,
                role=role,
                provider_id=provider.id if tenant is None else None,
                tenant_id=tenant.id if tenant else None,
                permissions=permissions,
                password_hash=password_hash,
            )
        )

    user("admin@demo.example", "Dana Whitfield", Role.PROVIDER_ADMIN)
    user("shop@demo.example", "Rusty Kemp", Role.PROVIDER_LIMITED, permissions="maintenance")
    user("academy@demo.example", "Lena Ortiz", Role.PROVIDER_LIMITED, permissions="training")
    user("owner@demo.example", "Cal Brennan", Role.CARRIER_ADMIN, tenant=tenants["medium"])
    user("viewer@demo.example", "Jo Marsh", Role.CARRIER_VIEWER, tenant=tenants["medium"])
    user("small-owner@demo.example", "Mae Collins", Role.CARRIER_ADMIN, tenant=tenants["small"])
    user("large-owner@demo.example", "Wes Harlan", Role.CARRIER_ADMIN, tenant=tenants["large"])

"""Builders for test data. All names and numbers are fictional."""

from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import (
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
    Vehicle,
)
from app.tenancy import all_tenants

TODAY = date(2026, 11, 10)


def make_provider(name: str = "Test Compliance Co.") -> Provider:
    provider = Provider(name=name)
    db.session.add(provider)
    db.session.flush()
    return provider


def make_tenant(provider: Provider, name: str) -> Tenant:
    tenant = Tenant(provider_id=provider.id, name=name, dot_number="0000000", mc_number="MC-000")
    db.session.add(tenant)
    db.session.flush()
    return tenant


def populate_tenant(tenant: Tenant, prefix: str) -> dict[str, object]:
    """Give a tenant one row in every tenant-scoped table. Returns them by model name."""
    tid = tenant.id
    with all_tenants():
        driver = Driver(
            tenant_id=tid,
            first_name=f"{prefix}First",
            last_name=f"{prefix}Last",
            cdl_number=f"{prefix}-CDL-1",
            cdl_class="A",
            cdl_expiration=TODAY + timedelta(days=400),
            medical_card_expiration=TODAY + timedelta(days=200),
        )
        vehicle = Vehicle(tenant_id=tid, unit_number=f"{prefix}-101", vehicle_type="tractor")
        db.session.add_all([driver, vehicle])
        db.session.flush()
        dvir = DVIR(tenant_id=tid, vehicle_id=vehicle.id, driver_id=driver.id, inspected_on=TODAY)
        db.session.add(dvir)
        db.session.flush()
        rows = {
            "Driver": driver,
            "Vehicle": vehicle,
            "DVIR": dvir,
            "DriverFileItem": DriverFileItem(
                tenant_id=tid, driver_id=driver.id, item_type="mvr", completed_on=TODAY
            ),
            "DrugAlcoholTest": DrugAlcoholTest(
                tenant_id=tid,
                driver_id=driver.id,
                test_type="random",
                tested_on=TODAY,
                result="negative",
            ),
            "TrainingRecord": TrainingRecord(
                tenant_id=tid, driver_id=driver.id, course_name="Hazmat", completed_on=TODAY
            ),
            "HOSLog": HOSLog(tenant_id=tid, driver_id=driver.id, log_date=TODAY, driving_hours=8),
            "MaintenanceRecord": MaintenanceRecord(
                tenant_id=tid, vehicle_id=vehicle.id, performed_on=TODAY, work_done="PM service"
            ),
            "ImportTemplate": ImportTemplate(tenant_id=tid, name="Monthly", data_type="drivers"),
            "ImportRun": ImportRun(tenant_id=tid, data_type="drivers", file_name="d.xlsx"),
            "IntegrationConnection": IntegrationConnection(tenant_id=tid, service="motive"),
            "AuditLog": AuditLog(tenant_id=tid, action="test"),
        }
        db.session.add_all(rows.values())
        db.session.commit()
    return rows


DEMO_PASSWORD = "demo-pass-123"


def make_user(
    email: str,
    role: str,
    *,
    provider: Provider | None = None,
    tenant: Tenant | None = None,
    permissions: str = "",
    password: str = DEMO_PASSWORD,
    active: bool = True,
):
    from app.auth.services import hash_password
    from app.models import User

    user = User(
        email=email,
        name=email.split("@")[0].title(),
        role=role,
        provider_id=provider.id if provider else None,
        tenant_id=tenant.id if tenant else None,
        permissions=permissions,
        password_hash=hash_password(password),
        active=active,
    )
    db.session.add(user)
    db.session.commit()
    return user

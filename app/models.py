"""Database models.

Every table that holds a carrier's compliance data inherits ``TenantScoped``,
which adds a required ``tenant_id`` and puts the table under the automatic
tenant filter in ``app/tenancy.py``.

All identifiers in seed and sample data (DOT, MC, CDL numbers, VINs) are fake.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db
from .tenancy import TenantScoped


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    PROVIDER_ADMIN = "provider_admin"
    PROVIDER_LIMITED = "provider_limited"
    CARRIER_ADMIN = "carrier_admin"
    CARRIER_VIEWER = "carrier_viewer"


class TenantKind(StrEnum):
    CARRIER = "carrier"
    ACADEMY = "academy"


class DriverStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class FileItemType(StrEnum):
    APPLICATION = "application"
    MVR = "mvr"
    ROAD_TEST = "road_test"
    PREVIOUS_EMPLOYER_CHECK = "previous_employer_check"
    ANNUAL_REVIEW = "annual_review"


class DrugTestType(StrEnum):
    PRE_EMPLOYMENT = "pre_employment"
    RANDOM = "random"
    POST_ACCIDENT = "post_accident"


class DrugTestResult(StrEnum):
    NEGATIVE = "negative"
    POSITIVE = "positive"
    REFUSED = "refused"
    PENDING = "pending"


class TrainingCategory(StrEnum):
    ACADEMY = "academy"
    HAZMAT = "hazmat"
    SAFETY = "safety"


class VehicleType(StrEnum):
    TRACTOR = "tractor"
    TRAILER = "trailer"


class ShopType(StrEnum):
    IN_HOUSE = "in_house"
    OUTSIDE = "outside"


class RepairStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Provider, tenants and users (not tenant-scoped: needed to log in and to route)
# ---------------------------------------------------------------------------


class Provider(TimestampMixin, db.Model):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))

    tenants: Mapped[list[Tenant]] = relationship(back_populates="provider")


class Tenant(TimestampMixin, db.Model):
    """One carrier client (or the academy's own fleet) managed by the provider."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default=TenantKind.CARRIER)
    dot_number: Mapped[str | None] = mapped_column(String(20))
    mc_number: Mapped[str | None] = mapped_column(String(20))
    address_line: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(10))

    provider: Mapped[Provider] = relationship(back_populates="tenants")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role IN ('provider_admin', 'provider_limited') AND provider_id IS NOT NULL "
            "AND tenant_id IS NULL) OR "
            "(role IN ('carrier_admin', 'carrier_viewer') AND tenant_id IS NOT NULL)",
            name="role_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"))
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    # Provider Limited users: comma-separated areas, e.g. "maintenance" or "training".
    permissions: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provider: Mapped[Provider | None] = relationship()
    tenant: Mapped[Tenant | None] = relationship()


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


class Driver(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "drivers"
    __table_args__ = (UniqueConstraint("tenant_id", "cdl_number", name="uq_drivers_tenant_cdl"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(60))
    last_name: Mapped[str] = mapped_column(String(60))
    cdl_number: Mapped[str] = mapped_column(String(30))
    cdl_state: Mapped[str | None] = mapped_column(String(2))
    cdl_class: Mapped[str | None] = mapped_column(String(2))
    cdl_expiration: Mapped[date | None] = mapped_column(Date)
    medical_card_expiration: Mapped[date | None] = mapped_column(Date)
    hire_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=DriverStatus.ACTIVE)
    is_student: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(30))

    file_items: Mapped[list[DriverFileItem]] = relationship(
        back_populates="driver", cascade="all, delete-orphan"
    )
    tests: Mapped[list[DrugAlcoholTest]] = relationship(
        back_populates="driver", cascade="all, delete-orphan"
    )
    trainings: Mapped[list[TrainingRecord]] = relationship(
        back_populates="driver", cascade="all, delete-orphan"
    )
    hos_logs: Mapped[list[HOSLog]] = relationship(
        back_populates="driver", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class DriverFileItem(TenantScoped, TimestampMixin, db.Model):
    """One item in a driver qualification file (application, MVR, road test...)."""

    __tablename__ = "driver_file_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(40))
    completed_on: Mapped[date | None] = mapped_column(Date)
    due_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    driver: Mapped[Driver] = relationship(back_populates="file_items")


class DrugAlcoholTest(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "drug_alcohol_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    test_type: Mapped[str] = mapped_column(String(30))
    tested_on: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(20))

    driver: Mapped[Driver] = relationship(back_populates="tests")


class TrainingRecord(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "training_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    course_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20), default=TrainingCategory.SAFETY)
    completed_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)

    driver: Mapped[Driver] = relationship(back_populates="trainings")


class HOSLog(TenantScoped, TimestampMixin, db.Model):
    """One driver-day of hours of service, as synced from the ELD."""

    __tablename__ = "hos_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "driver_id", "log_date", name="uq_hos_driver_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    log_date: Mapped[date] = mapped_column(Date, index=True)
    driving_hours: Mapped[float] = mapped_column(Float, default=0)
    on_duty_hours: Mapped[float] = mapped_column(Float, default=0)
    off_duty_hours: Mapped[float] = mapped_column(Float, default=0)
    violation: Mapped[bool] = mapped_column(Boolean, default=False)
    violation_note: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(40), default="Motive (mock)")
    external_id: Mapped[str | None] = mapped_column(String(60))

    driver: Mapped[Driver] = relationship(back_populates="hos_logs")


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


class Vehicle(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_number", name="uq_vehicles_tenant_unit"),
        UniqueConstraint("tenant_id", "vin", name="uq_vehicles_tenant_vin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_number: Mapped[str] = mapped_column(String(20))
    vehicle_type: Mapped[str] = mapped_column(String(20))
    make: Mapped[str | None] = mapped_column(String(40))
    year: Mapped[int | None] = mapped_column(Integer)
    vin: Mapped[str | None] = mapped_column(String(17))
    plate: Mapped[str | None] = mapped_column(String(15))
    plate_state: Mapped[str | None] = mapped_column(String(2))
    registration_expiration: Mapped[date | None] = mapped_column(Date)
    annual_inspection_on: Mapped[date | None] = mapped_column(Date)
    odometer: Mapped[int | None] = mapped_column(Integer)
    in_service: Mapped[bool] = mapped_column(Boolean, default=True)

    maintenance: Mapped[list[MaintenanceRecord]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )
    dvirs: Mapped[list[DVIR]] = relationship(back_populates="vehicle", cascade="all, delete-orphan")


class DVIR(TenantScoped, TimestampMixin, db.Model):
    """Driver vehicle inspection report."""

    __tablename__ = "dvirs"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id", ondelete="SET NULL"))
    inspected_on: Mapped[date] = mapped_column(Date, index=True)
    defects: Mapped[str | None] = mapped_column(Text)
    defect_found: Mapped[bool] = mapped_column(Boolean, default=False)
    defect_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(40), default="Motive (mock)")
    external_id: Mapped[str | None] = mapped_column(String(60))

    vehicle: Mapped[Vehicle] = relationship(back_populates="dvirs")
    driver: Mapped[Driver | None] = relationship()
    repairs: Mapped[list[MaintenanceRecord]] = relationship(back_populates="dvir")


class MaintenanceRecord(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    dvir_id: Mapped[int | None] = mapped_column(ForeignKey("dvirs.id", ondelete="SET NULL"))
    performed_on: Mapped[date] = mapped_column(Date)
    work_done: Mapped[str] = mapped_column(String(300))
    shop_type: Mapped[str] = mapped_column(String(20), default=ShopType.IN_HOUSE)
    shop_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default=RepairStatus.COMPLETED)
    next_due_on: Mapped[date | None] = mapped_column(Date)
    next_due_miles: Mapped[int | None] = mapped_column(Integer)

    vehicle: Mapped[Vehicle] = relationship(back_populates="maintenance")
    dvir: Mapped[DVIR | None] = relationship(back_populates="repairs")


# ---------------------------------------------------------------------------
# Imports, integrations and audit
# ---------------------------------------------------------------------------


class ImportTemplate(TenantScoped, TimestampMixin, db.Model):
    """A saved column mapping, so next month's spreadsheet imports in one click."""

    __tablename__ = "import_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "data_type", "name", name="uq_import_template_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    data_type: Mapped[str] = mapped_column(String(30))
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ImportRun(TenantScoped, TimestampMixin, db.Model):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    data_type: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str] = mapped_column(String(255))
    rows_added: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    # What the import changed, so the last import can be undone:
    # [{"model": "Driver", "id": 7, "action": "added"|"updated", "before": {...}}]
    changes: Mapped[list] = mapped_column(JSON, default=list)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship()


class IntegrationConnection(TenantScoped, TimestampMixin, db.Model):
    """Per-tenant link to an outside system (Motive ELD for now)."""

    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("tenant_id", "service", name="uq_integration_service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service: Mapped[str] = mapped_column(String(30), default="motive")
    status: Mapped[str] = mapped_column(String(30), default="demo")
    # Name of the environment variable or secret-store entry that holds this
    # tenant's API key. The key itself is never stored in the database.
    api_key_ref: Mapped[str | None] = mapped_column(String(120))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(TenantScoped, db.Model):
    """Who changed what, when. Rows are written by the audit hook, never edited."""

    __tablename__ = "audit_logs"
    __tenant_nullable__ = True  # provider-level actions have no tenant

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))
    table_name: Mapped[str | None] = mapped_column(String(60))
    record_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(String(300))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User | None] = relationship()


TENANT_SCOPED_MODELS: tuple[type[TenantScoped], ...] = (
    Driver,
    DriverFileItem,
    DrugAlcoholTest,
    TrainingRecord,
    HOSLog,
    Vehicle,
    DVIR,
    MaintenanceRecord,
    ImportTemplate,
    ImportRun,
    IntegrationConnection,
    AuditLog,
)

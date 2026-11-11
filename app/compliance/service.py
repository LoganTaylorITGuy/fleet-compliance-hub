"""Load drivers and vehicles efficiently and apply the compliance rules.

Runs inside whatever tenant scope is active: in a carrier's scope you get that
carrier; inside ``all_tenants()`` (provider dashboard) you get every tenant,
grouped by tenant_id. There is no tenant filter here, by design: that's
``app/tenancy.py``'s job.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Driver, HOSLog, Vehicle
from . import thresholds as t
from .rules import Finding, Level, Status, driver_status, vehicle_status


@dataclass
class DriverRow:
    driver: Driver
    status: Status


@dataclass
class VehicleRow:
    vehicle: Vehicle
    status: Status


@dataclass
class Counts:
    red: int = 0
    yellow: int = 0
    green: int = 0

    def add(self, level: Level) -> None:
        setattr(self, level.key, getattr(self, level.key) + 1)

    @property
    def total(self) -> int:
        return self.red + self.yellow + self.green


@dataclass
class TenantSummary:
    tenant_id: int
    drivers: list[DriverRow] = field(default_factory=list)
    vehicles: list[VehicleRow] = field(default_factory=list)

    @property
    def driver_counts(self) -> Counts:
        return _count(row.status.level for row in self.drivers)

    @property
    def vehicle_counts(self) -> Counts:
        return _count(row.status.level for row in self.vehicles)

    @property
    def counts(self) -> Counts:
        return _count(row.status.level for row in [*self.drivers, *self.vehicles])

    @property
    def urgency(self) -> tuple[int, int]:
        """Sort key for the provider dashboard: most reds first, then most yellows."""
        c = self.counts
        return (-c.red, -c.yellow)

    def items(self, level: Level) -> list[tuple[object, Finding]]:
        """Every (driver or vehicle, finding) pair at ``level``, soonest due first."""
        pairs = [
            (row.driver, f) for row in self.drivers for f in row.status.findings if f.level == level
        ] + [
            (row.vehicle, f)
            for row in self.vehicles
            for f in row.status.findings
            if f.level == level
        ]
        return sorted(pairs, key=lambda p: p[1].due or date.max)

    @property
    def expiring_soon(self) -> list[tuple[object, Finding]]:
        return self.items(Level.YELLOW)

    @property
    def needs_action(self) -> list[tuple[object, Finding]]:
        return self.items(Level.RED)


def _count(levels) -> Counts:
    counts = Counts()
    for level in levels:
        counts.add(level)
    return counts


def load_drivers(today: date, *, driver_ids: list[int] | None = None) -> list[Driver]:
    """Active drivers with everything the rules need, in a handful of queries."""
    hos_cutoff = today - timedelta(days=t.HOS_VIOLATION_LOOKBACK_DAYS)
    stmt = (
        select(Driver)
        .where(Driver.status.not_in(t.INACTIVE_DRIVER_STATUSES))
        .options(
            selectinload(Driver.file_items),
            selectinload(Driver.tests),
            selectinload(Driver.trainings),
            selectinload(Driver.hos_logs.and_(HOSLog.log_date >= hos_cutoff)),
        )
        .order_by(Driver.last_name, Driver.first_name)
    )
    if driver_ids is not None:
        stmt = stmt.where(Driver.id.in_(driver_ids))
    return list(db.session.scalars(stmt))


def load_vehicles(*, vehicle_ids: list[int] | None = None) -> list[Vehicle]:
    stmt = (
        select(Vehicle)
        .options(selectinload(Vehicle.maintenance), selectinload(Vehicle.dvirs))
        .order_by(Vehicle.vehicle_type, Vehicle.unit_number)
    )
    if vehicle_ids is not None:
        stmt = stmt.where(Vehicle.id.in_(vehicle_ids))
    return list(db.session.scalars(stmt))


def evaluate(today: date | None = None) -> dict[int, TenantSummary]:
    """Compliance status for every driver and unit visible in the current scope."""
    today = today or date.today()
    summaries: dict[int, TenantSummary] = defaultdict(lambda: TenantSummary(0))
    for driver in load_drivers(today):
        summary = summaries[driver.tenant_id]
        summary.tenant_id = driver.tenant_id
        summary.drivers.append(DriverRow(driver, driver_status(driver, today)))
    for vehicle in load_vehicles():
        summary = summaries[vehicle.tenant_id]
        summary.tenant_id = vehicle.tenant_id
        summary.vehicles.append(VehicleRow(vehicle, vehicle_status(vehicle, today)))
    return dict(summaries)

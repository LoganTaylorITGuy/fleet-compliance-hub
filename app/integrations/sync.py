"""Pull data from Motive into the current tenant.

Incremental, like a real ELD sync: hours of service are fetched from the day
after the newest synced log through today (today's log is refreshed on every
sync, since it's still in progress), DVIRs for the last two days, and current
odometers. Past days already synced are never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select

from .. import audit
from ..extensions import db
from ..imports.engine import normalize_key
from ..models import DVIR, Driver, HOSLog, IntegrationConnection, Vehicle
from .motive import MockRoster, MotiveClient, RosterDriver, RosterVehicle

# Simplified HOS limits used to flag violations in synced logs (illustration only).
DRIVING_LIMIT_HOURS = 11
ON_DUTY_LIMIT_HOURS = 14
DVIR_LOOKBACK_DAYS = 1


@dataclass
class SyncResult:
    hos_added: int = 0
    hos_updated: int = 0
    dvirs_added: int = 0
    odometers_updated: int = 0
    unmatched: int = 0

    def summary(self) -> str:
        text = (
            f"Motive sync: {self.hos_added} HOS logs added, {self.hos_updated} updated, "
            f"{self.dvirs_added} DVIRs added, {self.odometers_updated} odometers updated"
        )
        return text + (f", {self.unmatched} records unmatched" if self.unmatched else "")


def get_connection() -> IntegrationConnection:
    """This tenant's Motive connection, created on first use."""
    connection = db.session.scalars(
        select(IntegrationConnection).where(IntegrationConnection.service == "motive")
    ).first()
    if connection is None:
        connection = IntegrationConnection(service="motive", status="demo")
        db.session.add(connection)
        db.session.flush()
    return connection


def build_client(now: datetime) -> MotiveClient:
    drivers = db.session.scalars(select(Driver).where(Driver.is_student.is_(False))).all()
    vehicles = db.session.scalars(select(Vehicle)).all()
    roster = MockRoster(
        drivers=[RosterDriver(d.id, d.first_name, d.last_name, d.cdl_number) for d in drivers],
        vehicles=[RosterVehicle(v.id, v.unit_number, v.vehicle_type, v.odometer) for v in vehicles],
    )
    return MotiveClient(
        current_app.config["MOTIVE_API_KEY"],
        demo_mode=current_app.config["DEMO_MODE"],
        roster=roster,
        now=now,
    )


def sync_motive(now: datetime) -> SyncResult:
    """Run one sync for the current tenant scope and commit it."""
    today = now.date()
    client = build_client(now)
    result = SyncResult()

    with audit.audit_suppressed():
        drivers_by_motive_id = _match_drivers(client, result)
        _sync_hos(client, drivers_by_motive_id, today, result)
        vehicles_by_motive_id = _sync_vehicles(client, result)
        _sync_dvirs(client, drivers_by_motive_id, vehicles_by_motive_id, today, result)
        connection = get_connection()
        connection.last_synced_at = datetime.now(UTC)
        connection.status = "demo" if client.demo_mode else "connected"
        audit.record("sync", result.summary(), table_name="integration_connections")
    db.session.commit()
    return result


def _match_drivers(client: MotiveClient, result: SyncResult) -> dict[str, Driver]:
    local = {normalize_key(d.cdl_number): d for d in db.session.scalars(select(Driver))}
    matched = {}
    for record in client.get_drivers()["data"]:
        driver = local.get(normalize_key(record.get("license_number")))
        if driver is None:
            result.unmatched += 1
            continue
        matched[record["id"]] = driver
    return matched


def _sync_hos(client, drivers: dict[str, Driver], today: date, result: SyncResult) -> None:
    newest = db.session.scalar(select(func.max(HOSLog.log_date)).where(HOSLog.log_date < today))
    start = (newest + timedelta(days=1)) if newest else today - timedelta(days=7)
    existing = {
        (log.driver_id, log.log_date): log
        for log in db.session.scalars(select(HOSLog).where(HOSLog.log_date >= start))
    }
    for record in client.get_hos_logs(start, today)["data"]:
        driver = drivers.get(record["driver_id"])
        if driver is None:
            result.unmatched += 1
            continue
        day = date.fromisoformat(record["date"])
        driving, on_duty = record["driving_hours"], record["on_duty_hours"]
        violation = (
            bool(record.get("violations"))
            or driving > DRIVING_LIMIT_HOURS
            or on_duty > ON_DUTY_LIMIT_HOURS
        )
        values = {
            "driving_hours": driving,
            "on_duty_hours": on_duty,
            "off_duty_hours": record["off_duty_hours"]
            if record["off_duty_hours"] is not None
            else round(24 - on_duty, 2),
            "violation": violation,
            "violation_note": "Limit exceeded (from ELD)" if violation else None,
            "source": "Motive (mock)" if client.demo_mode else "Motive",
            "external_id": record["id"],
        }
        log = existing.get((driver.id, day))
        if log is None:
            db.session.add(HOSLog(driver_id=driver.id, log_date=day, **values))
            result.hos_added += 1
        elif any(getattr(log, k) != v for k, v in values.items()):
            for key, value in values.items():
                setattr(log, key, value)
            result.hos_updated += 1


def _sync_vehicles(client, result: SyncResult) -> dict[str, Vehicle]:
    local = {normalize_key(v.unit_number): v for v in db.session.scalars(select(Vehicle))}
    matched = {}
    for record in client.get_vehicles()["data"]:
        vehicle = local.get(normalize_key(record.get("number")))
        if vehicle is None:
            result.unmatched += 1
            continue
        matched[record["id"]] = vehicle
        odometer = record.get("current_odometer_miles")
        if odometer and (vehicle.odometer is None or odometer > vehicle.odometer):
            vehicle.odometer = odometer
            result.odometers_updated += 1
    return matched


def _sync_dvirs(client, drivers, vehicles, today: date, result: SyncResult) -> None:
    start = today - timedelta(days=DVIR_LOOKBACK_DAYS)
    known = set(db.session.scalars(select(DVIR.external_id).where(DVIR.external_id.is_not(None))))
    for record in client.get_dvirs(start, today)["data"]:
        if record["id"] in known:
            continue
        vehicle = vehicles.get(record["vehicle_id"])
        if vehicle is None:
            result.unmatched += 1
            continue
        driver = drivers.get(record.get("driver_id"))
        defects = "; ".join(record.get("defects") or [])
        db.session.add(
            DVIR(
                vehicle_id=vehicle.id,
                driver_id=driver.id if driver else None,
                inspected_on=date.fromisoformat(record["date"]),
                defects=defects or None,
                defect_found=bool(defects),
                source="Motive (mock)" if client.demo_mode else "Motive",
                external_id=record["id"],
            )
        )
        result.dvirs_added += 1

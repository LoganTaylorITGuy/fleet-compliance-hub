"""Match imported rows to records that already exist in this tenant.

Each import type has a Resolver: ``load`` reads the tenant's existing records
once per file, and ``match`` turns one parsed row into a Match: the row's
duplicate-detection key, the existing record it updates (or None to add), and
an error if the row can't be placed (for example, a training record for a CDL
number that isn't on file).

Queries run inside the current tenant scope, so lookups only ever see this
carrier's drivers and units.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from sqlalchemy import select

from ..extensions import db
from ..identifiers import normalize_key
from ..models import Driver, DrugAlcoholTest, MaintenanceRecord, TrainingRecord, Vehicle


class Match(NamedTuple):
    key: tuple | None
    target: Any  # the existing record this row updates, or None to add
    error: str | None = None


@dataclass(frozen=True)
class Resolver:
    key_field: str  # the column errors are reported against
    load: Callable[[], Any]
    match: Callable[[dict[str, Any], Any], Match]


NO_DRIVER = "No driver with that CDL number. Import drivers first."
NO_UNIT = "No unit with that number. Import vehicles first."


# --- lookups -------------------------------------------------------------------


def _drivers_by_cdl() -> dict[str, Driver]:
    return {normalize_key(d.cdl_number): d for d in db.session.scalars(select(Driver))}


def _vehicles() -> dict[str, dict[str, Vehicle]]:
    vehicles = db.session.scalars(select(Vehicle)).all()
    return {
        "unit": {normalize_key(v.unit_number): v for v in vehicles},
        "vin": {normalize_key(v.vin): v for v in vehicles if v.vin},
    }


def _load_training():
    existing = {
        (t.driver_id, t.course_name.lower()): t for t in db.session.scalars(select(TrainingRecord))
    }
    return _drivers_by_cdl(), existing


def _load_tests():
    existing = {
        (t.driver_id, t.test_type, t.tested_on): t
        for t in db.session.scalars(select(DrugAlcoholTest))
    }
    return _drivers_by_cdl(), existing


def _load_maintenance():
    existing = {
        (m.vehicle_id, m.performed_on, m.work_done.lower()): m
        for m in db.session.scalars(select(MaintenanceRecord))
    }
    return _vehicles()["unit"], existing


# --- matchers ------------------------------------------------------------------


def _match_driver(values: dict[str, Any], drivers: dict[str, Driver]) -> Match:
    key = normalize_key(values["cdl_number"])
    values["cdl_number"] = key
    return Match((key,), drivers.get(key))


def _match_vehicle(values: dict[str, Any], lookup: dict[str, dict[str, Vehicle]]) -> Match:
    """Match on unit number first, then VIN (units get renumbered; VINs don't)."""
    unit = normalize_key(values["unit_number"])
    values["unit_number"] = unit
    vin = normalize_key(values.get("vin")) or None
    if vin:
        values["vin"] = vin
    target = lookup["unit"].get(unit) or (lookup["vin"].get(vin) if vin else None)
    return Match((unit,), target)


def _match_training(values: dict[str, Any], lookup) -> Match:
    drivers, existing = lookup
    driver = drivers.get(normalize_key(values["cdl_number"]))
    if driver is None:
        return Match(None, None, NO_DRIVER)
    values["driver_id"] = driver.id
    key = (driver.id, values["course_name"].lower())
    return Match(key, existing.get(key))


def _match_test(values: dict[str, Any], lookup) -> Match:
    drivers, existing = lookup
    driver = drivers.get(normalize_key(values["cdl_number"]))
    if driver is None:
        return Match(None, None, NO_DRIVER)
    values["driver_id"] = driver.id
    key = (driver.id, values["test_type"], values["tested_on"])
    return Match(key, existing.get(key))


def _match_maintenance(values: dict[str, Any], lookup) -> Match:
    units, existing = lookup
    vehicle = units.get(normalize_key(values["unit_number"]))
    if vehicle is None:
        return Match(None, None, NO_UNIT)
    values["vehicle_id"] = vehicle.id
    key = (vehicle.id, values["performed_on"], values["work_done"].lower())
    return Match(key, existing.get(key))


RESOLVERS: dict[str, Resolver] = {
    "drivers": Resolver("cdl_number", _drivers_by_cdl, _match_driver),
    "vehicles": Resolver("unit_number", _vehicles, _match_vehicle),
    "training": Resolver("cdl_number", _load_training, _match_training),
    "drug_tests": Resolver("cdl_number", _load_tests, _match_test),
    "maintenance": Resolver("unit_number", _load_maintenance, _match_maintenance),
}

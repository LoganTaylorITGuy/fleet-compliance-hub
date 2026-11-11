"""Validate mapped rows, commit them, and undo an import.

Runs inside the current tenant scope like everything else: lookups only see
this carrier's drivers and units, and new rows are stamped with its tenant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select

from .. import audit
from ..extensions import db
from ..models import (
    Driver,
    DrugAlcoholTest,
    ImportRun,
    MaintenanceRecord,
    TrainingRecord,
    Vehicle,
    utcnow,
)
from .parsing import parse_bool, parse_date, parse_int
from .specs import ImportSpec

MODELS = {
    "Driver": Driver,
    "Vehicle": Vehicle,
    "TrainingRecord": TrainingRecord,
    "DrugAlcoholTest": DrugAlcoholTest,
    "MaintenanceRecord": MaintenanceRecord,
}


@dataclass
class RowResult:
    index: int
    raw: dict[str, str]
    values: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    action: str = "add"  # add | update
    target: Any = None  # the existing record an update applies to
    skipped: bool = False

    @property
    def line(self) -> int:
        """Spreadsheet line number (header is line 1)."""
        return self.index + 2

    @property
    def ok(self) -> bool:
        return not self.errors and not self.skipped


def normalize_key(text: str | None) -> str:
    return re.sub(r"[\s\-]", "", (text or "")).upper()


# --- building and validating -------------------------------------------------


def build_rows(
    spec: ImportSpec,
    headers: list[str],
    rows: list[list[str]],
    mapping: dict[str, str],
    overrides: dict[str, dict[str, str]] | None = None,
    skipped: set[int] | None = None,
) -> list[RowResult]:
    overrides = overrides or {}
    skipped = skipped or set()
    column_for = {
        target: headers.index(h) for h, target in mapping.items() if target and h in headers
    }
    results = []
    for index, row in enumerate(rows):
        raw = {name: row[col] if col < len(row) else "" for name, col in column_for.items()}
        raw.update(overrides.get(str(index), {}))
        result = RowResult(index=index, raw=raw, skipped=index in skipped)
        _parse_fields(spec, result)
        results.append(result)
    _resolve(spec, results)
    return results


def _parse_fields(spec: ImportSpec, result: RowResult) -> None:
    for f in spec.fields:
        text = result.raw.get(f.name, "").strip()
        if not text:
            if f.required:
                result.errors[f.name] = f"{f.label} is required"
            result.values[f.name] = None
            continue
        try:
            result.values[f.name] = _parse_value(f, text)
        except ValueError as exc:
            result.errors[f.name] = str(exc)
    if spec.key == "drivers":
        _split_name(result)


def _parse_value(f, text: str):
    match f.kind:
        case "date":
            return parse_date(text)
        case "int":
            return parse_int(text)
        case "bool":
            return parse_bool(text)
        case "choice":
            word = text.strip().lower()
            if word in f.choices:
                return f.choices[word]
            if word in f.choices.values():
                return word
            options = ", ".join(sorted(set(f.choices.values())))
            raise ValueError(f'"{text}" isn\'t a valid {f.label.lower()} (use {options})')
    if len(text) > f.max_length:
        raise ValueError(f"{f.label} is longer than {f.max_length} characters")
    return text


def _split_name(result: RowResult) -> None:
    values = result.values
    if not values.get("first_name") and not values.get("last_name") and values.get("full_name"):
        full = values["full_name"]
        if "," in full:  # "Ruiz, Ana"
            last, _, first = full.partition(",")
        else:
            first, _, last = full.rpartition(" ")
        values["first_name"], values["last_name"] = first.strip(), last.strip()
    if not values.get("first_name") or not values.get("last_name"):
        result.errors.setdefault("full_name", "First and last name are required")


def _resolve(spec: ImportSpec, results: list[RowResult]) -> None:
    """Match rows to existing records and flag duplicates within the file."""
    resolver = RESOLVERS[spec.key]
    lookup = resolver.load()
    seen: dict[tuple, int] = {}
    for r in results:
        if r.errors:
            continue
        key, target, error = resolver.match(r.values, lookup)
        if error:
            r.errors[resolver.key_field] = error
            continue
        if key in seen:
            r.errors[resolver.key_field] = f"Duplicate of line {seen[key]} in this file"
            continue
        if not r.skipped:
            seen[key] = r.line
        r.target = target
        r.action = "update" if target is not None else "add"


@dataclass
class Resolver:
    key_field: str
    load: Any
    match: Any


def _drivers_by_cdl() -> dict[str, Driver]:
    return {normalize_key(d.cdl_number): d for d in db.session.scalars(select(Driver))}


def _vehicles() -> dict[str, dict[str, Vehicle]]:
    vehicles = db.session.scalars(select(Vehicle)).all()
    return {
        "unit": {normalize_key(v.unit_number): v for v in vehicles},
        "vin": {normalize_key(v.vin): v for v in vehicles if v.vin},
    }


def _match_driver(values, lookup):
    key = normalize_key(values["cdl_number"])
    values["cdl_number"] = key
    return (key,), lookup.get(key), None


def _match_vehicle(values, lookup):
    unit = normalize_key(values["unit_number"])
    values["unit_number"] = unit
    vin = normalize_key(values.get("vin")) or None
    if vin:
        values["vin"] = vin
    target = lookup["unit"].get(unit) or (lookup["vin"].get(vin) if vin else None)
    return (unit,), target, None


def _load_training():
    drivers = _drivers_by_cdl()
    existing = {
        (t.driver_id, t.course_name.lower()): t for t in db.session.scalars(select(TrainingRecord))
    }
    return drivers, existing


def _match_training(values, lookup):
    drivers, existing = lookup
    driver = drivers.get(normalize_key(values["cdl_number"]))
    if driver is None:
        return None, None, "No driver with that CDL number. Import drivers first."
    values["driver_id"] = driver.id
    key = (driver.id, values["course_name"].lower())
    return key, existing.get(key), None


def _load_tests():
    drivers = _drivers_by_cdl()
    existing = {
        (t.driver_id, t.test_type, t.tested_on): t
        for t in db.session.scalars(select(DrugAlcoholTest))
    }
    return drivers, existing


def _match_test(values, lookup):
    drivers, existing = lookup
    driver = drivers.get(normalize_key(values["cdl_number"]))
    if driver is None:
        return None, None, "No driver with that CDL number. Import drivers first."
    values["driver_id"] = driver.id
    key = (driver.id, values["test_type"], values["tested_on"])
    return key, existing.get(key), None


def _load_maintenance():
    units = _vehicles()["unit"]
    existing = {
        (m.vehicle_id, m.performed_on, m.work_done.lower()): m
        for m in db.session.scalars(select(MaintenanceRecord))
    }
    return units, existing


def _match_maintenance(values, lookup):
    units, existing = lookup
    vehicle = units.get(normalize_key(values["unit_number"]))
    if vehicle is None:
        return None, None, "No unit with that number. Import vehicles first."
    values["vehicle_id"] = vehicle.id
    key = (vehicle.id, values["performed_on"], values["work_done"].lower())
    return key, existing.get(key), None


RESOLVERS = {
    "drivers": Resolver("cdl_number", _drivers_by_cdl, _match_driver),
    "vehicles": Resolver("unit_number", _vehicles, _match_vehicle),
    "training": Resolver("cdl_number", _load_training, _match_training),
    "drug_tests": Resolver("cdl_number", _load_tests, _match_test),
    "maintenance": Resolver("unit_number", _load_maintenance, _match_maintenance),
}

# Which parsed values are written to the model, per import type.
WRITE_FIELDS = {
    "drivers": (
        Driver,
        [
            "first_name",
            "last_name",
            "cdl_number",
            "cdl_state",
            "cdl_class",
            "cdl_expiration",
            "medical_card_expiration",
            "hire_date",
            "phone",
            "status",
            "is_student",
        ],
    ),
    "vehicles": (
        Vehicle,
        [
            "unit_number",
            "vehicle_type",
            "make",
            "year",
            "vin",
            "plate",
            "plate_state",
            "registration_expiration",
            "annual_inspection_on",
        ],
    ),
    "training": (
        TrainingRecord,
        ["driver_id", "course_name", "category", "completed_on", "expires_on"],
    ),
    "drug_tests": (DrugAlcoholTest, ["driver_id", "test_type", "tested_on", "result"]),
    "maintenance": (
        MaintenanceRecord,
        [
            "vehicle_id",
            "performed_on",
            "work_done",
            "shop_type",
            "shop_name",
            "next_due_on",
            "next_due_miles",
        ],
    ),
}


# --- commit and undo -----------------------------------------------------------


def _plain(value):
    return value.isoformat() if isinstance(value, date) else value


def commit(
    spec: ImportSpec, results: list[RowResult], *, file_name: str, user_id: int | None
) -> ImportRun:
    """Write every valid, non-skipped row. Caller has checked there are no errors."""
    model, names = WRITE_FIELDS[spec.key]
    run = ImportRun(
        data_type=spec.key,
        file_name=file_name,
        user_id=user_id,
        rows_added=0,
        rows_updated=0,
        rows_skipped=0,
    )
    changes = []
    with audit.audit_suppressed():  # one summary entry instead of one per row
        for r in results:
            if r.skipped:
                run.rows_skipped += 1
                continue
            # Blank cells don't erase existing data on update.
            data = {n: r.values.get(n) for n in names if r.values.get(n) is not None}
            if r.action == "update":
                obj = r.target
                before = {n: _plain(getattr(obj, n)) for n in data}
                changed = {n: v for n, v in data.items() if getattr(obj, n) != v}
                if not changed:
                    run.rows_skipped += 1
                    continue
                for name, value in changed.items():
                    setattr(obj, name, value)
                run.rows_updated += 1
                changes.append(
                    {"model": model.__name__, "id": obj.id, "action": "updated", "before": before}
                )
            else:
                obj = model(**data)
                db.session.add(obj)
                db.session.flush()
                run.rows_added += 1
                changes.append({"model": model.__name__, "id": obj.id, "action": "added"})
        run.changes = changes
        db.session.add(run)
        db.session.flush()
        audit.record(
            "import",
            f"{spec.label} import from {file_name}: {run.rows_added} added, "
            f"{run.rows_updated} updated, {run.rows_skipped} skipped",
            table_name="import_runs",
            record_id=run.id,
        )
    db.session.commit()
    return run


def latest_run() -> ImportRun | None:
    """The most recent import in this tenant, if it hasn't been undone."""
    run = db.session.scalars(select(ImportRun).order_by(ImportRun.id.desc())).first()
    return run if run and run.undone_at is None else None


def undo(run: ImportRun) -> tuple[int, int]:
    """Reverse an import: delete what it added, restore what it updated."""
    removed = restored = 0
    with audit.audit_suppressed():
        for change in reversed(run.changes or []):
            model = MODELS[change["model"]]
            obj = db.session.scalars(select(model).where(model.id == change["id"])).first()
            if obj is None:
                continue
            if change["action"] == "added":
                db.session.delete(obj)
                removed += 1
            else:
                for name, value in change["before"].items():
                    column_type = model.__table__.columns[name].type.python_type
                    if value is not None and column_type is date:
                        value = date.fromisoformat(value)
                    setattr(obj, name, value)
                restored += 1
        run.undone_at = utcnow()
        audit.record(
            "undo_import",
            f"Undid import of {run.file_name}: {removed} removed, {restored} restored",
            table_name="import_runs",
            record_id=run.id,
        )
    db.session.commit()
    return removed, restored

"""What each import type expects: fields, header synonyms, and how rows match.

Adding an import type means three entries: an ImportSpec here, a Resolver in
resolvers.py (how rows match existing records), and a WRITE_FIELDS entry in
engine.py (which parsed values are saved).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from .parsing import normalize_header


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str = "text"  # text | date | int | bool | choice
    required: bool = False
    synonyms: tuple[str, ...] = ()
    choices: dict[str, str] = field(default_factory=dict)  # spreadsheet word -> stored value
    max_length: int = 120


@dataclass(frozen=True)
class ImportSpec:
    key: str
    label: str
    fields: tuple[FieldSpec, ...]
    match_help: str

    def field(self, name: str) -> FieldSpec:
        return next(f for f in self.fields if f.name == name)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


DRIVER_STATUS = {
    "active": "active",
    "a": "active",
    "on leave": "on_leave",
    "leave": "on_leave",
    "loa": "on_leave",
    "terminated": "terminated",
    "termed": "terminated",
    "inactive": "terminated",
}
VEHICLE_TYPES = {
    "tractor": "tractor",
    "truck": "tractor",
    "power unit": "tractor",
    "pu": "tractor",
    "trailer": "trailer",
    "trl": "trailer",
    "tr": "trailer",
}
TEST_TYPES = {
    "pre employment": "pre_employment",
    "pre-employment": "pre_employment",
    "preemployment": "pre_employment",
    "random": "random",
    "post accident": "post_accident",
    "post-accident": "post_accident",
}
TEST_RESULTS = {
    "negative": "negative",
    "neg": "negative",
    "positive": "positive",
    "pos": "positive",
    "refused": "refused",
    "refusal": "refused",
    "pending": "pending",
}
TRAINING_CATEGORIES = {"academy": "academy", "hazmat": "hazmat", "safety": "safety"}
SHOP_TYPES = {
    "in house": "in_house",
    "in-house": "in_house",
    "inhouse": "in_house",
    "our shop": "in_house",
    "outside": "outside",
    "vendor": "outside",
    "dealer": "outside",
}


SPECS: dict[str, ImportSpec] = {
    "drivers": ImportSpec(
        "drivers",
        "Drivers",
        (
            FieldSpec(
                "full_name",
                "Full name (split into first and last)",
                synonyms=("driver name", "name", "driver", "employee name"),
            ),
            FieldSpec("first_name", "First name", synonyms=("first", "fname", "given name")),
            FieldSpec("last_name", "Last name", synonyms=("last", "lname", "surname")),
            FieldSpec(
                "cdl_number",
                "CDL number",
                required=True,
                synonyms=(
                    "cdl",
                    "cdl no",
                    "cdl num",
                    "license number",
                    "license",
                    "dl number",
                    "lic number",
                ),
                max_length=30,
            ),
            FieldSpec(
                "cdl_state",
                "CDL state",
                synonyms=("state", "lic state", "license state", "dl state"),
                max_length=2,
            ),
            FieldSpec("cdl_class", "CDL class", synonyms=("class", "license class"), max_length=2),
            FieldSpec(
                "cdl_expiration",
                "CDL expiration",
                kind="date",
                synonyms=(
                    "cdl exp",
                    "cdl expires",
                    "license exp",
                    "license expiration",
                    "cdl exp date",
                ),
            ),
            FieldSpec(
                "medical_card_expiration",
                "Medical card expiration",
                kind="date",
                synonyms=(
                    "med card",
                    "med card exp",
                    "medical card",
                    "medical exp",
                    "dot physical",
                    "dot physical exp",
                    "physical exp",
                    "medical certificate",
                ),
            ),
            FieldSpec(
                "hire_date",
                "Hire date",
                kind="date",
                synonyms=("hired", "date hired", "start date", "doh"),
            ),
            FieldSpec(
                "phone",
                "Phone",
                synonyms=("cell", "mobile", "phone number", "cell phone"),
                max_length=30,
            ),
            FieldSpec(
                "status",
                "Status",
                kind="choice",
                choices=DRIVER_STATUS,
                synonyms=("driver status", "employment status"),
            ),
            FieldSpec(
                "is_student", "Academy student", kind="bool", synonyms=("student", "trainee")
            ),
        ),
        "Drivers are matched by CDL number. A match updates the existing driver.",
    ),
    "vehicles": ImportSpec(
        "vehicles",
        "Vehicles",
        (
            FieldSpec(
                "unit_number",
                "Unit number",
                required=True,
                synonyms=(
                    "unit",
                    "unit no",
                    "truck number",
                    "truck no",
                    "trailer number",
                    "fleet number",
                ),
                max_length=20,
            ),
            FieldSpec(
                "vehicle_type",
                "Type (tractor or trailer)",
                kind="choice",
                required=True,
                choices=VEHICLE_TYPES,
                synonyms=("type", "equipment type", "unit type"),
            ),
            FieldSpec("make", "Make", synonyms=("manufacturer", "mfr"), max_length=40),
            FieldSpec("year", "Year", kind="int", synonyms=("model year", "yr")),
            FieldSpec(
                "vin", "VIN", synonyms=("vin number", "serial", "serial number"), max_length=17
            ),
            FieldSpec(
                "plate",
                "Plate",
                synonyms=("tag", "license plate", "plate number", "tag number"),
                max_length=15,
            ),
            FieldSpec(
                "plate_state", "Plate state", synonyms=("tag state", "plate st"), max_length=2
            ),
            FieldSpec(
                "registration_expiration",
                "Registration expiration",
                kind="date",
                synonyms=("reg exp", "registration", "registration exp", "tag exp", "reg expires"),
            ),
            FieldSpec(
                "annual_inspection_on",
                "Last annual inspection",
                kind="date",
                synonyms=(
                    "annual insp",
                    "annual inspection",
                    "last annual",
                    "dot inspection",
                    "annual",
                ),
            ),
        ),
        "Units are matched by unit number, then by VIN. A match updates the existing unit.",
    ),
    "training": ImportSpec(
        "training",
        "Training",
        (
            FieldSpec(
                "cdl_number",
                "Driver CDL number",
                required=True,
                synonyms=("cdl", "cdl no", "license number", "driver cdl"),
                max_length=30,
            ),
            FieldSpec(
                "course_name",
                "Course",
                required=True,
                synonyms=("course", "class name", "training", "training course"),
                max_length=120,
            ),
            FieldSpec(
                "category",
                "Category",
                kind="choice",
                choices=TRAINING_CATEGORIES,
                synonyms=("type", "training type"),
            ),
            FieldSpec(
                "completed_on",
                "Completed",
                kind="date",
                synonyms=("completed", "completion date", "date completed"),
            ),
            FieldSpec(
                "expires_on",
                "Expires",
                kind="date",
                synonyms=("expires", "expiration", "exp date", "valid until"),
            ),
        ),
        "Matched by driver CDL number and course name. The driver must already exist.",
    ),
    "drug_tests": ImportSpec(
        "drug_tests",
        "Drug and alcohol tests",
        (
            FieldSpec(
                "cdl_number",
                "Driver CDL number",
                required=True,
                synonyms=("cdl", "cdl no", "license number", "driver cdl"),
                max_length=30,
            ),
            FieldSpec(
                "test_type",
                "Test type",
                kind="choice",
                required=True,
                choices=TEST_TYPES,
                synonyms=("type", "reason", "test reason"),
            ),
            FieldSpec(
                "tested_on",
                "Test date",
                kind="date",
                required=True,
                synonyms=("date", "collection date", "test date"),
            ),
            FieldSpec(
                "result",
                "Result",
                kind="choice",
                required=True,
                choices=TEST_RESULTS,
                synonyms=("outcome", "test result"),
            ),
        ),
        "Matched by driver CDL number, test type and date. The driver must already exist.",
    ),
    "maintenance": ImportSpec(
        "maintenance",
        "Maintenance",
        (
            FieldSpec(
                "unit_number",
                "Unit number",
                required=True,
                synonyms=("unit", "unit no", "truck", "trailer"),
                max_length=20,
            ),
            FieldSpec(
                "performed_on",
                "Date",
                kind="date",
                required=True,
                synonyms=("date", "service date", "repair date"),
            ),
            FieldSpec(
                "work_done",
                "Work done",
                required=True,
                synonyms=("work", "description", "service", "repair", "notes"),
                max_length=300,
            ),
            FieldSpec(
                "shop_type",
                "Shop type",
                kind="choice",
                choices=SHOP_TYPES,
                synonyms=("shop", "where"),
            ),
            FieldSpec("shop_name", "Shop name", synonyms=("vendor", "shop name"), max_length=120),
            FieldSpec(
                "next_due_on",
                "Next service due",
                kind="date",
                synonyms=("next due", "next service", "next pm"),
            ),
            FieldSpec(
                "next_due_miles",
                "Next service due (miles)",
                kind="int",
                synonyms=("next miles", "next due miles", "next odometer"),
            ),
        ),
        "Matched by unit, date and work done. The unit must already exist.",
    ),
}


def suggest_mapping(spec: ImportSpec, headers: list[str]) -> dict[str, str]:
    """Guess which field each spreadsheet column holds. Returns {header: field or ""}.

    Exact name or synonym first, then a close fuzzy match. Each field is used
    at most once, so two columns never land in the same field.
    """
    vocabulary: dict[str, str] = {}
    for f in spec.fields:
        vocabulary[normalize_header(f.name)] = f.name
        vocabulary[normalize_header(f.label)] = f.name
        for synonym in f.synonyms:
            vocabulary[normalize_header(synonym)] = f.name

    mapping: dict[str, str] = {}
    used: set[str] = set()
    pending = []
    for header in headers:
        norm = normalize_header(header)
        target = vocabulary.get(norm)
        if target and target not in used:
            mapping[header] = target
            used.add(target)
        else:
            pending.append((header, norm))
    for header, norm in pending:
        close = difflib.get_close_matches(norm, vocabulary.keys(), n=3, cutoff=0.75)
        target = next((vocabulary[c] for c in close if vocabulary[c] not in used), "")
        mapping[header] = target
        if target:
            used.add(target)
    return mapping

"""The shape of the demo data set: tenants, courses and fixed values.

Change these to change what gets seeded; generator.py turns them into rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..models import TenantKind, TrainingCategory

SEED = 2026
HOS_DAYS = 30
TRAILER_SHOP = "In-house trailer shop"

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # VINs never use I, O or Q


@dataclass(frozen=True)
class TenantPlan:
    key: str
    name: str
    kind: str
    city: str
    drivers: int
    tractors: int
    trailers: int
    students: int = 0


def tenant_plans() -> list[TenantPlan]:
    academy = os.environ.get("DEMO_ACADEMY_NAME", "").strip() or "High Plains Driving Academy"
    return [
        TenantPlan("small", "Cedar Mesa Freight LLC", TenantKind.CARRIER, "Canyon", 3, 3, 3),
        TenantPlan("medium", "Red Draw Hauling Co.", TenantKind.CARRIER, "Hereford", 8, 6, 8),
        TenantPlan("large", "Blue Stem Transport Inc.", TenantKind.CARRIER, "Amarillo", 15, 12, 16),
        TenantPlan("academy", academy, TenantKind.ACADEMY, "Hereford", 2, 3, 2, students=6),
    ]


ACADEMY_COURSES = [
    "CDL Class A: Theory (ELDT)",
    "CDL Class A: Range Skills (ELDT)",
    "CDL Class A: Road Skills (ELDT)",
    "Pre-trip Inspection",
]
SAFETY_COURSES = [
    ("Defensive Driving", TrainingCategory.SAFETY, 730),
    ("Hazmat Endorsement Training", TrainingCategory.HAZMAT, 1095),
    ("Winter Driving Safety", TrainingCategory.SAFETY, 365),
    ("Cargo Securement", TrainingCategory.SAFETY, 730),
]

"""Red / yellow / green compliance rules.

Pure functions: they take model objects (with their related lists already
loaded) and a ``today`` date, and touch no database. Every rule has a unit test.

* **Red:** anything expired, a failed test, an unresolved DVIR defect, or an
  HOS violation in the last 7 days.
* **Yellow:** anything due within 30 days (or a test result still pending).
* **Green:** everything current.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum

from ..formatting import label as humanize
from . import thresholds as t


class Level(IntEnum):
    GREEN = 0
    YELLOW = 1
    RED = 2

    @property
    def text(self) -> str:
        return {Level.GREEN: "Current", Level.YELLOW: "Due soon", Level.RED: "Action needed"}[self]

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Finding:
    """One reason an item isn't green."""

    level: Level
    category: str  # "cdl", "medical", "file", "test", "training", "hos", "registration", ...
    label: str  # "Medical card", "MVR", "Registration"...
    message: str  # "Expires in 12 days (2026-11-29)"
    due: date | None = None


@dataclass
class Status:
    findings: list[Finding] = field(default_factory=list)

    @property
    def level(self) -> Level:
        return max((f.level for f in self.findings), default=Level.GREEN)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (-f.level, f.due or date.max))


def date_finding(
    when: date | None,
    today: date,
    *,
    category: str,
    label: str,
    verb: str = "Expires",
    missing_is_red: bool = False,
) -> Finding | None:
    """Turn an expiration or due date into a red/yellow finding, or None if current."""
    if when is None:
        if missing_is_red:
            return Finding(Level.RED, category, label, "Not on file")
        return None
    days = (when - today).days
    if days < 0:
        past = "Expired" if verb == "Expires" else "Overdue"
        return Finding(Level.RED, category, label, f"{past} {when.isoformat()}", when)
    if days <= t.WARNING_DAYS:
        when_text = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
        return Finding(
            Level.YELLOW, category, label, f"{verb} {when_text} ({when.isoformat()})", when
        )
    return None


def _keep(findings: Iterable[Finding | None]) -> list[Finding]:
    return [f for f in findings if f is not None]


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


def driver_status(driver, today: date) -> Status:
    findings: list[Finding | None] = [
        date_finding(
            driver.cdl_expiration,
            today,
            category="cdl",
            label="CDL",
            missing_is_red=not driver.is_student,
        ),
        date_finding(
            driver.medical_card_expiration,
            today,
            category="medical",
            label="Medical card",
            missing_is_red=True,
        ),
    ]
    findings += file_item_findings(driver.file_items, today)
    findings += drug_test_findings(driver.tests)
    findings += training_findings(driver.trainings, today)
    findings += hos_findings(driver.hos_logs, today)
    return Status(_keep(findings))


def file_item_findings(items, today: date) -> list[Finding | None]:
    return [
        date_finding(
            item.due_on, today, category="file", label=_file_label(item.item_type), verb="Due"
        )
        for item in items
    ]


def _file_label(item_type: str) -> str:
    return {"mvr": "MVR"}.get(item_type, humanize(item_type))


def drug_test_findings(tests) -> list[Finding]:
    """Only the most recent test counts: a later negative test clears an earlier one."""
    if not tests:
        return []
    latest = max(tests, key=lambda x: (x.tested_on, x.id or 0))
    kind = humanize(latest.test_type)
    if latest.result in t.FAILED_TEST_RESULTS:
        return [
            Finding(
                Level.RED,
                "test",
                f"{kind} test",
                f"{humanize(latest.result)} on {latest.tested_on.isoformat()}",
                latest.tested_on,
            )
        ]
    if latest.result in t.PENDING_TEST_RESULTS:
        return [
            Finding(
                Level.YELLOW,
                "test",
                f"{kind} test",
                f"Result pending since {latest.tested_on.isoformat()}",
                latest.tested_on,
            )
        ]
    return []


def training_findings(trainings, today: date) -> list[Finding | None]:
    return [
        date_finding(tr.expires_on, today, category="training", label=tr.course_name)
        for tr in trainings
    ]


def hos_findings(logs, today: date) -> list[Finding]:
    cutoff = today - timedelta(days=t.HOS_VIOLATION_LOOKBACK_DAYS)
    recent = sorted(
        (log for log in logs if log.violation and cutoff <= log.log_date <= today),
        key=lambda log: log.log_date,
        reverse=True,
    )
    return [
        Finding(
            Level.RED,
            "hos",
            "Hours of service",
            f"{log.violation_note or 'Violation'} on {log.log_date.isoformat()}",
            log.log_date,
        )
        for log in recent
    ]


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


def vehicle_status(vehicle, today: date) -> Status:
    findings: list[Finding | None] = [
        date_finding(
            vehicle.registration_expiration,
            today,
            category="registration",
            label="Registration",
            missing_is_red=True,
        ),
        annual_inspection_finding(vehicle.annual_inspection_on, today),
        maintenance_finding(vehicle.maintenance, today),
    ]
    findings += dvir_findings(vehicle.dvirs)
    return Status(_keep(findings))


def annual_inspection_due(last: date | None) -> date | None:
    return last + timedelta(days=t.ANNUAL_INSPECTION_INTERVAL_DAYS) if last else None


def annual_inspection_finding(last: date | None, today: date) -> Finding | None:
    return date_finding(
        annual_inspection_due(last),
        today,
        category="inspection",
        label="Annual inspection",
        verb="Due",
        missing_is_red=True,
    )


def next_maintenance_due(records) -> date | None:
    """The next-due date from the most recent record that sets one."""
    scheduled = [r for r in records if r.next_due_on]
    if not scheduled:
        return None
    return max(scheduled, key=lambda r: (r.performed_on, r.id or 0)).next_due_on


def maintenance_finding(records, today: date) -> Finding | None:
    return date_finding(
        next_maintenance_due(records),
        today,
        category="maintenance",
        label="Preventive maintenance",
        verb="Due",
    )


def dvir_findings(dvirs) -> list[Finding]:
    return [
        Finding(
            Level.RED,
            "dvir",
            "DVIR defect",
            f"Open since {d.inspected_on.isoformat()}: {d.defects or 'defect reported'}",
            d.inspected_on,
        )
        for d in sorted(dvirs, key=lambda d: d.inspected_on)
        if d.defect_found and not d.defect_resolved
    ]

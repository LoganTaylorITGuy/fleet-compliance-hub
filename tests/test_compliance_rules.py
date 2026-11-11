"""Unit tests for every red / yellow / green rule. No database needed."""

from datetime import date, timedelta

import pytest

from app.compliance import thresholds
from app.compliance.rules import (
    Level,
    annual_inspection_due,
    date_finding,
    driver_status,
    next_maintenance_due,
    vehicle_status,
)
from app.models import (
    DVIR,
    Driver,
    DriverFileItem,
    DrugAlcoholTest,
    HOSLog,
    MaintenanceRecord,
    TrainingRecord,
    Vehicle,
)

TODAY = date(2026, 11, 18)


def d(days: int) -> date:
    return TODAY + timedelta(days=days)


def clean_driver(**overrides) -> Driver:
    """A driver with everything current. Tests change one thing at a time."""
    fields = {
        "first_name": "Ana",
        "last_name": "Ruiz",
        "cdl_number": "991",
        "cdl_expiration": d(400),
        "medical_card_expiration": d(200),
        "is_student": False,
    }
    fields.update(overrides)
    return Driver(**fields)


def clean_vehicle(**overrides) -> Vehicle:
    fields = {
        "unit_number": "T101",
        "vehicle_type": "tractor",
        "registration_expiration": d(200),
        "annual_inspection_on": d(-100),
    }
    fields.update(overrides)
    return Vehicle(**fields)


def levels(status) -> set[tuple[str, Level]]:
    return {(f.category, f.level) for f in status.findings}


# --- date_finding boundaries ------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-1, Level.RED),
        (0, Level.YELLOW),
        (1, Level.YELLOW),
        (30, Level.YELLOW),
        (31, None),
        (365, None),
    ],
)
def test_date_finding_boundaries(offset, expected):
    finding = date_finding(d(offset), TODAY, category="x", label="X")
    assert (finding.level if finding else None) == expected


def test_date_finding_messages():
    assert date_finding(d(-2), TODAY, category="x", label="X").message.startswith("Expired")
    overdue = date_finding(d(-2), TODAY, category="x", label="X", verb="Due")
    assert overdue.message.startswith("Overdue")
    assert "today" in date_finding(TODAY, TODAY, category="x", label="X").message
    assert "in 1 day " in date_finding(d(1), TODAY, category="x", label="X").message
    assert "in 12 days" in date_finding(d(12), TODAY, category="x", label="X").message


def test_missing_date_is_red_only_when_required():
    assert date_finding(None, TODAY, category="x", label="X") is None
    assert (
        date_finding(None, TODAY, category="x", label="X", missing_is_red=True).level == Level.RED
    )


def test_warning_window_comes_from_thresholds(monkeypatch):
    monkeypatch.setattr(thresholds, "WARNING_DAYS", 60)
    assert date_finding(d(45), TODAY, category="x", label="X").level == Level.YELLOW


# --- drivers ----------------------------------------------------------------


def test_clean_driver_is_green():
    status = driver_status(clean_driver(), TODAY)
    assert status.level == Level.GREEN
    assert status.level.text == "Current"
    assert status.findings == []


def test_expired_medical_card_is_red():
    status = driver_status(clean_driver(medical_card_expiration=d(-1)), TODAY)
    assert levels(status) == {("medical", Level.RED)}


def test_medical_card_due_soon_is_yellow():
    status = driver_status(clean_driver(medical_card_expiration=d(12)), TODAY)
    assert status.level == Level.YELLOW
    assert "in 12 days" in status.findings[0].message


def test_missing_medical_card_is_red():
    assert driver_status(clean_driver(medical_card_expiration=None), TODAY).level == Level.RED


def test_expired_cdl_is_red_and_soon_is_yellow():
    assert driver_status(clean_driver(cdl_expiration=d(-5)), TODAY).level == Level.RED
    assert driver_status(clean_driver(cdl_expiration=d(25)), TODAY).level == Level.YELLOW


def test_missing_cdl_red_for_drivers_but_not_students():
    assert driver_status(clean_driver(cdl_expiration=None), TODAY).level == Level.RED
    student = clean_driver(cdl_expiration=None, is_student=True)
    assert driver_status(student, TODAY).level == Level.GREEN


def test_driver_file_item_overdue_and_due_soon():
    overdue = clean_driver(file_items=[DriverFileItem(item_type="mvr", due_on=d(-3))])
    status = driver_status(overdue, TODAY)
    assert levels(status) == {("file", Level.RED)}
    assert status.findings[0].label == "MVR"
    soon = clean_driver(file_items=[DriverFileItem(item_type="annual_review", due_on=d(20))])
    status = driver_status(soon, TODAY)
    assert status.level == Level.YELLOW
    assert status.findings[0].label == "Annual review"


def test_file_item_without_due_date_is_fine():
    driver = clean_driver(file_items=[DriverFileItem(item_type="application", completed_on=d(-9))])
    assert driver_status(driver, TODAY).level == Level.GREEN


@pytest.mark.parametrize("result", ["positive", "refused"])
def test_failed_test_is_red(result):
    driver = clean_driver(
        tests=[DrugAlcoholTest(test_type="random", tested_on=d(-4), result=result)]
    )
    assert levels(driver_status(driver, TODAY)) == {("test", Level.RED)}


def test_pending_test_is_yellow():
    driver = clean_driver(
        tests=[DrugAlcoholTest(test_type="post_accident", tested_on=d(-1), result="pending")]
    )
    assert driver_status(driver, TODAY).level == Level.YELLOW


def test_later_negative_test_clears_earlier_failure():
    driver = clean_driver(
        tests=[
            DrugAlcoholTest(test_type="random", tested_on=d(-90), result="positive"),
            DrugAlcoholTest(test_type="random", tested_on=d(-10), result="negative"),
        ]
    )
    assert driver_status(driver, TODAY).level == Level.GREEN


def test_training_expiry():
    expired = clean_driver(trainings=[TrainingRecord(course_name="Hazmat", expires_on=d(-1))])
    assert levels(driver_status(expired, TODAY)) == {("training", Level.RED)}
    soon = clean_driver(trainings=[TrainingRecord(course_name="Hazmat", expires_on=d(29))])
    assert driver_status(soon, TODAY).level == Level.YELLOW
    no_expiry = clean_driver(trainings=[TrainingRecord(course_name="Range skills")])
    assert driver_status(no_expiry, TODAY).level == Level.GREEN


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [(0, Level.RED), (2, Level.RED), (7, Level.RED), (8, Level.GREEN), (-1, Level.GREEN)],
)
def test_hos_violation_window(days_ago, expected):
    log = HOSLog(log_date=d(-days_ago), violation=True, violation_note="11-hour limit")
    assert driver_status(clean_driver(hos_logs=[log]), TODAY).level == expected


def test_hos_logs_without_violation_are_fine():
    log = HOSLog(log_date=d(-1), violation=False, driving_hours=10)
    assert driver_status(clean_driver(hos_logs=[log]), TODAY).level == Level.GREEN


def test_worst_finding_wins_and_findings_sort_worst_first():
    driver = clean_driver(
        medical_card_expiration=d(10),
        hos_logs=[HOSLog(log_date=d(-1), violation=True)],
    )
    status = driver_status(driver, TODAY)
    assert status.level == Level.RED
    assert [f.level for f in status.sorted_findings()] == [Level.RED, Level.YELLOW]


# --- vehicles ---------------------------------------------------------------


def test_clean_vehicle_is_green():
    assert vehicle_status(clean_vehicle(), TODAY).level == Level.GREEN


def test_registration_expired_soon_and_missing():
    assert vehicle_status(clean_vehicle(registration_expiration=d(-1)), TODAY).level == Level.RED
    assert vehicle_status(clean_vehicle(registration_expiration=d(15)), TODAY).level == Level.YELLOW
    assert vehicle_status(clean_vehicle(registration_expiration=None), TODAY).level == Level.RED


def test_annual_inspection_due_one_interval_after_last():
    assert annual_inspection_due(date(2026, 1, 1)) == date(2027, 1, 1)
    assert annual_inspection_due(None) is None


@pytest.mark.parametrize(
    ("last_offset", "expected"),
    [(-366, Level.RED), (-350, Level.YELLOW), (-100, Level.GREEN)],
)
def test_annual_inspection_status(last_offset, expected):
    vehicle = clean_vehicle(annual_inspection_on=d(last_offset))
    assert vehicle_status(vehicle, TODAY).level == expected


def test_missing_annual_inspection_is_red():
    assert vehicle_status(clean_vehicle(annual_inspection_on=None), TODAY).level == Level.RED


def test_maintenance_uses_most_recent_schedule():
    records = [
        MaintenanceRecord(performed_on=d(-200), work_done="PM", next_due_on=d(-100)),
        MaintenanceRecord(performed_on=d(-20), work_done="PM", next_due_on=d(70)),
        MaintenanceRecord(performed_on=d(-5), work_done="Tires"),  # no schedule
    ]
    assert next_maintenance_due(records) == d(70)
    assert vehicle_status(clean_vehicle(maintenance=records), TODAY).level == Level.GREEN


def test_maintenance_overdue_and_due_soon():
    overdue = [MaintenanceRecord(performed_on=d(-90), work_done="PM", next_due_on=d(-1))]
    assert vehicle_status(clean_vehicle(maintenance=overdue), TODAY).level == Level.RED
    soon = [MaintenanceRecord(performed_on=d(-60), work_done="PM", next_due_on=d(10))]
    assert vehicle_status(clean_vehicle(maintenance=soon), TODAY).level == Level.YELLOW


def test_unresolved_dvir_defect_is_red_resolved_is_not():
    open_defect = DVIR(
        inspected_on=d(-1), defect_found=True, defect_resolved=False, defects="Air leak"
    )
    fixed = DVIR(inspected_on=d(-9), defect_found=True, defect_resolved=True, defects="Light out")
    clean = DVIR(inspected_on=d(-2), defect_found=False)
    status = vehicle_status(clean_vehicle(dvirs=[open_defect, fixed, clean]), TODAY)
    assert levels(status) == {("dvir", Level.RED)}
    assert "Air leak" in status.findings[0].message
    assert vehicle_status(clean_vehicle(dvirs=[fixed, clean]), TODAY).level == Level.GREEN

"""Motive stub client, the sync job, and the Integrations page."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.integrations.motive import (
    MockRoster,
    MotiveClient,
    MotiveNotConfigured,
    RosterDriver,
    RosterVehicle,
)
from app.integrations.sync import sync_motive
from app.models import DVIR, AuditLog, HOSLog, IntegrationConnection, Vehicle
from app.tenancy import all_tenants, tenant_scope

NOW = datetime(2026, 11, 17, 14, 30)  # demo "today" is 2026-11-17
RED_DRAW = "Red Draw Hauling Co."
BLUE_STEM = "Blue Stem Transport Inc."

ROSTER = MockRoster(
    drivers=[RosterDriver(1, "Ana", "Ruiz", "99111111"), RosterDriver(2, "Sam", "Lee", "99222222")],
    vehicles=[
        RosterVehicle(10, "T101", "tractor", 100_000),
        RosterVehicle(11, "TR501", "trailer", None),
    ],
)


# --- client --------------------------------------------------------------------


def test_requires_key_outside_demo_mode():
    with pytest.raises(MotiveNotConfigured):
        MotiveClient(None, demo_mode=False)


def test_live_calls_are_not_implemented():
    client = MotiveClient("key-from-env", demo_mode=False)
    with pytest.raises(NotImplementedError, match="DEMO_MODE"):
        client.get_drivers()


def test_mock_responses_are_rest_shaped():
    client = MotiveClient(None, demo_mode=True, roster=ROSTER, now=NOW)
    for response in (
        client.get_drivers(),
        client.get_vehicles(),
        client.get_hos_logs(NOW.date() - timedelta(days=2), NOW.date()),
        client.get_dvirs(NOW.date() - timedelta(days=5), NOW.date()),
    ):
        assert set(response) == {"data", "pagination"}
        assert response["pagination"]["total"] == len(response["data"])
    drivers = client.get_drivers()["data"]
    assert drivers[0] == {
        "id": "mock-drv-1",
        "first_name": "Ana",
        "last_name": "Ruiz",
        "license_number": "99111111",
        "status": "active",
    }
    assert client.mode_label == "Connected (demo mode)"


def test_mock_hos_is_deterministic_and_never_future():
    client = MotiveClient(None, demo_mode=True, roster=ROSTER, now=NOW)
    end = NOW.date() + timedelta(days=3)
    first = client.get_hos_logs(NOW.date() - timedelta(days=3), end)["data"]
    second = client.get_hos_logs(NOW.date() - timedelta(days=3), end)["data"]
    assert first == second
    assert max(r["date"] for r in first) == NOW.date().isoformat()
    today = [r for r in first if r["in_progress"]]
    assert len(today) == 2 and all(r["off_duty_hours"] is None for r in today)


def test_todays_hours_grow_through_the_day():
    early = MotiveClient(None, demo_mode=True, roster=ROSTER, now=NOW.replace(hour=7))
    late = MotiveClient(None, demo_mode=True, roster=ROSTER, now=NOW.replace(hour=17))
    today = NOW.date()
    e = sum(r["driving_hours"] for r in early.get_hos_logs(today, today)["data"])
    lt = sum(r["driving_hours"] for r in late.get_hos_logs(today, today)["data"])
    assert e <= lt


def test_odometer_only_for_tractors():
    vehicles = MotiveClient(None, demo_mode=True, roster=ROSTER, now=NOW).get_vehicles()["data"]
    assert vehicles[0]["current_odometer_miles"] > 100_000
    assert vehicles[1]["current_odometer_miles"] is None


# --- sync ------------------------------------------------------------------------


def _counts(tenant_id):
    with all_tenants():
        return {
            "hos": db.session.scalar(
                select(func.count()).select_from(HOSLog).where(HOSLog.tenant_id == tenant_id)
            ),
            "dvirs": db.session.scalar(
                select(func.count()).select_from(DVIR).where(DVIR.tenant_id == tenant_id)
            ),
        }


def test_sync_adds_today_and_is_idempotent(demo):
    red = demo["tenants"][RED_DRAW]
    before = _counts(red)
    with tenant_scope(red):
        first = sync_motive(NOW)
    assert first.hos_added == 8  # one in-progress log per working driver
    assert first.dvirs_added > 0
    assert first.odometers_updated > 0
    after = _counts(red)
    assert after["hos"] == before["hos"] + 8
    with tenant_scope(red):
        second = sync_motive(NOW)
    assert (second.hos_added, second.dvirs_added) == (0, 0)
    assert _counts(red) == after


def test_sync_refreshes_todays_log_later_in_the_day(demo):
    red = demo["tenants"][RED_DRAW]
    with tenant_scope(red):
        sync_motive(NOW.replace(hour=8))
        later = sync_motive(NOW.replace(hour=16))
    assert later.hos_updated > 0 and later.hos_added == 0


def test_sync_never_rewrites_history(demo):
    """The planted violation two days ago must survive any number of syncs."""
    red = demo["tenants"][RED_DRAW]
    two_days_ago = demo["today"] - timedelta(days=2)
    with tenant_scope(red):
        sync_motive(NOW)
        sync_motive(NOW)
        violations = db.session.scalars(
            select(HOSLog).where(HOSLog.violation.is_(True), HOSLog.log_date == two_days_ago)
        ).all()
    assert len(violations) == 1
    assert violations[0].violation_note == "11-hour driving limit exceeded"


def test_sync_records_audit_summary_and_timestamp(demo):
    red = demo["tenants"][RED_DRAW]
    with tenant_scope(red):
        sync_motive(NOW)
        entry = db.session.scalars(select(AuditLog).where(AuditLog.action == "sync")).one()
        connection = db.session.scalars(select(IntegrationConnection)).one()
    assert entry.summary.startswith("Motive sync: 8 HOS logs added")
    assert connection.last_synced_at.date() >= date(2026, 11, 10)


@pytest.mark.isolation
def test_sync_only_touches_current_tenant(demo):
    red, blue = demo["tenants"][RED_DRAW], demo["tenants"][BLUE_STEM]
    blue_before = _counts(blue)
    with all_tenants():
        blue_odometers = dict(
            db.session.execute(
                select(Vehicle.id, Vehicle.odometer).where(Vehicle.tenant_id == blue)
            ).all()
        )
    with tenant_scope(red):
        sync_motive(NOW)
    assert _counts(blue) == blue_before
    with all_tenants():
        assert (
            dict(
                db.session.execute(
                    select(Vehicle.id, Vehicle.odometer).where(Vehicle.tenant_id == blue)
                ).all()
            )
            == blue_odometers
        )


def test_violation_flagged_from_hours(demo, monkeypatch):
    red = demo["tenants"][RED_DRAW]

    def long_day(self, driver, day, *, in_progress):
        return {
            "id": f"x-{driver.local_id}-{day}",
            "driver_id": f"mock-drv-{driver.local_id}",
            "date": day.isoformat(),
            "driving_hours": 11.5,
            "on_duty_hours": 13.0,
            "off_duty_hours": 11.0,
            "in_progress": False,
            "violations": [],
        }

    monkeypatch.setattr(MotiveClient, "_mock_log", long_day)
    with tenant_scope(red):
        sync_motive(NOW)
        flagged = db.session.scalars(
            select(HOSLog).where(HOSLog.log_date == NOW.date(), HOSLog.violation.is_(True))
        ).all()
    assert len(flagged) == 8


# --- page --------------------------------------------------------------------------


def test_integrations_page_and_sync_button(demo, demo_login, monkeypatch):
    monkeypatch.setattr("app.integrations.routes.local_now", lambda: NOW)
    client = demo_login("owner@demo.example")
    html = client.get("/integrations/").get_data(as_text=True)
    assert "Connected (demo mode)" in html
    assert "Sync now" in html
    assert "Not set (not needed in demo mode)" in html
    response = client.post("/integrations/motive/sync", follow_redirects=True)
    text = response.get_data(as_text=True)
    assert "Motive sync: 8 HOS logs added" in text
    assert "Recent syncs" in text


def test_viewer_cannot_see_or_run_sync(demo, demo_login):
    client = demo_login("viewer@demo.example")
    assert client.get("/integrations/").status_code == 403
    assert client.post("/integrations/motive/sync").status_code == 403


def test_sync_refuses_without_demo_or_key(demo, demo_login, app):
    app.config["DEMO_MODE"] = False
    try:
        client = demo_login("owner@demo.example")
        html = client.get("/integrations/").get_data(as_text=True)
        assert "Not connected" in html and "Sync now" not in html
        response = client.post("/integrations/motive/sync", follow_redirects=True)
        assert "Sync didn&#39;t run" in response.get_data(as_text=True)
    finally:
        app.config["DEMO_MODE"] = True

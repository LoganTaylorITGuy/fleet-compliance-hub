"""Drivers, Fleet, Hours of Service and Training pages."""

from sqlalchemy import select

from app.extensions import db
from app.models import DVIR, AuditLog, Driver, MaintenanceRecord, TrainingRecord, Vehicle
from app.tenancy import all_tenants

RED_DRAW = "Red Draw Hauling Co."
BLUE_STEM = "Blue Stem Transport Inc."
ACADEMY = "High Plains Driving Academy"


def _first(model, tenant_id, *where):
    with all_tenants():
        obj = db.session.scalars(
            select(model).where(model.tenant_id == tenant_id, *where).order_by(model.id)
        ).first()
        if obj is not None:
            db.session.expunge(obj)  # detach just this record; keep the logged-in user
        return obj


def _open_repair(demo):
    with all_tenants():
        record = db.session.scalars(
            select(MaintenanceRecord).where(MaintenanceRecord.status == "open")
        ).one()
        return record.id, record.vehicle_id, record.dvir_id


# --- pages render for each role ---------------------------------------------------


def test_every_page_renders_for_carrier_admin(demo, demo_login):
    client = demo_login("owner@demo.example")
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    vehicle = _first(Vehicle, demo["tenants"][RED_DRAW])
    for path in (
        "/drivers/",
        f"/drivers/{driver.id}",
        "/fleet/",
        f"/fleet/{vehicle.id}",
        "/hours/",
        "/training/",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Demo only." in response.get_data(as_text=True)


def test_driver_search_and_status_filter(demo, demo_login):
    client = demo_login("owner@demo.example")
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    html = client.get(f"/drivers/?q={driver.cdl_number}").get_data(as_text=True)
    assert driver.full_name in html
    assert "1 shown" in html
    red = client.get("/drivers/?status=red").get_data(as_text=True)
    assert "Action needed" in red and "✓</span>Current" not in red


def test_driver_detail_shows_file_tests_training_and_hours(demo, demo_login):
    client = demo_login("owner@demo.example")
    driver = _first(Driver, demo["tenants"][RED_DRAW], Driver.medical_card_expiration == None)  # noqa: E711
    driver = driver or _first(Driver, demo["tenants"][RED_DRAW])
    html = client.get(f"/drivers/{driver.id}").get_data(as_text=True)
    for heading in (
        "Driver qualification file",
        "Drug and alcohol tests",
        "Training",
        "Hours of service, last 7 days",
        "Synced from Motive (mock)",
        "Previous employer check",
    ):
        assert heading in html


def test_fleet_type_filter(demo, demo_login):
    client = demo_login("owner@demo.example")
    html = client.get("/fleet/?type=trailer").get_data(as_text=True)
    assert "Trailer" in html and "Tractor ·" not in html


def test_open_dvir_trailer_shows_in_shop(demo, demo_login):
    client = demo_login("owner@demo.example")
    _, vehicle_id, _ = _open_repair(demo)
    html = client.get(f"/fleet/{vehicle_id}").get_data(as_text=True)
    assert "Open defect" in html
    assert "In shop now" in html
    assert "Mark repair complete" in html


def test_hos_highlights_violation_and_labels_source(demo, demo_login):
    html = demo_login("owner@demo.example").get("/hours/").get_data(as_text=True)
    assert "Synced from Motive (mock)" in html
    assert "1 violation</strong>" in html
    assert "violation: 11-hour driving limit exceeded" in html  # screen-reader text
    only = demo_login("owner@demo.example").get("/hours/?violations=1").get_data(as_text=True)
    assert only.count("<tr>") < html.count("<tr>")


def test_training_page_for_academy(demo, demo_login):
    html = demo_login("academy@demo.example", demo["tenants"][ACADEMY]).get("/training/")
    text = html.get_data(as_text=True)
    assert "Academy students" in text
    assert "Mark complete" in text
    assert 'role="progressbar"' in text


# --- edits are permission-checked and audited ---------------------------------------


def test_carrier_admin_edits_driver_and_it_is_audited(demo, demo_login):
    client = demo_login("owner@demo.example")
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    response = client.post(
        f"/drivers/{driver.id}/edit",
        data={
            "medical_card_expiration": "2028-01-31",
            "cdl_expiration": "2029-06-30",
            "status": "active",
            "phone": "806-555-0100",
        },
    )
    assert response.status_code == 302
    with all_tenants():
        entry = db.session.scalars(
            select(AuditLog).where(
                AuditLog.table_name == "drivers",
                AuditLog.record_id == driver.id,
                AuditLog.action == "update",
            )
        ).one()
    assert entry.after["medical_card_expiration"] == "2028-01-31"
    assert entry.user_id is not None


def test_invalid_edit_is_rejected(demo, demo_login):
    client = demo_login("owner@demo.example")
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    client.post(f"/drivers/{driver.id}/edit", data={"status": "bogus"})
    with all_tenants():
        assert db.session.scalars(select(Driver.status).where(Driver.id == driver.id)).one() != (
            "bogus"
        )


def test_viewer_and_shop_cannot_edit_drivers(demo, demo_login):
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    data = {"status": "active"}
    viewer = demo_login("viewer@demo.example")
    assert "Update record" not in viewer.get(f"/drivers/{driver.id}").get_data(as_text=True)
    assert viewer.post(f"/drivers/{driver.id}/edit", data=data).status_code == 403
    shop = demo_login("shop@demo.example", demo["tenants"][RED_DRAW])
    assert shop.post(f"/drivers/{driver.id}/edit", data=data).status_code == 403
    assert shop.get("/drivers/").status_code == 403  # shop staff see Fleet, not Drivers


def test_shop_completes_repair_and_dvir_is_resolved(demo, demo_login):
    record_id, vehicle_id, dvir_id = _open_repair(demo)
    client = demo_login("shop@demo.example", demo["tenants"][RED_DRAW])
    assert client.get(f"/fleet/{vehicle_id}").status_code == 200
    response = client.post(f"/fleet/maintenance/{record_id}/complete")
    assert response.status_code == 302
    with all_tenants():
        assert db.session.scalars(select(DVIR.defect_resolved).where(DVIR.id == dvir_id)).one()
        assert (
            db.session.scalars(
                select(MaintenanceRecord.status).where(MaintenanceRecord.id == record_id)
            ).one()
            == "completed"
        )
    again = client.post(f"/fleet/maintenance/{record_id}/complete", follow_redirects=True)
    assert "already complete" in again.get_data(as_text=True)


def test_viewer_cannot_complete_repair(demo, demo_login):
    record_id, _, _ = _open_repair(demo)
    client = demo_login("viewer@demo.example")
    assert client.post(f"/fleet/maintenance/{record_id}/complete").status_code == 403


def test_add_maintenance_record(demo, demo_login):
    client = demo_login("owner@demo.example")
    vehicle = _first(Vehicle, demo["tenants"][RED_DRAW])
    response = client.post(
        f"/fleet/{vehicle.id}/maintenance",
        data={
            "performed_on": "2026-11-16",
            "work_done": "Replaced wiper blades",
            "shop_type": "outside",
            "shop_name": "Panhandle Diesel Service",
        },
    )
    assert response.status_code == 302
    html = client.get(f"/fleet/{vehicle.id}").get_data(as_text=True)
    assert "Replaced wiper blades" in html
    bad = client.post(f"/fleet/{vehicle.id}/maintenance", data={"work_done": ""})
    assert bad.status_code == 302  # redirected back with an error, nothing saved


def test_academy_staff_marks_course_complete(demo, demo_login):
    academy = demo["tenants"][ACADEMY]
    course = _first(TrainingRecord, academy, TrainingRecord.completed_on.is_(None))
    client = demo_login("academy@demo.example", academy)
    assert client.post(f"/training/{course.id}/complete").status_code == 302
    with all_tenants():
        assert (
            db.session.scalars(
                select(TrainingRecord.completed_on).where(TrainingRecord.id == course.id)
            ).one()
            == demo["today"]
        )
    again = client.post(f"/training/{course.id}/complete", follow_redirects=True)
    assert "already complete" in again.get_data(as_text=True)


def test_viewer_cannot_complete_course(demo, demo_login):
    academy = demo["tenants"][ACADEMY]
    course = _first(TrainingRecord, academy, TrainingRecord.completed_on.is_(None))
    client = demo_login("viewer@demo.example")
    assert client.post(f"/training/{course.id}/complete").status_code == 403

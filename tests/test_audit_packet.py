"""Driver audit packet: what it shows, who may pull one, and that every pull is logged."""

from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select

from app.compliance import Level
from app.drivers.routes import file_rows
from app.extensions import db
from app.models import AuditLog, Driver, FileItemType
from app.tenancy import all_tenants

RED_DRAW = "Red Draw Hauling Co."
TODAY = date(2026, 11, 17)


def _red_draw_driver(demo) -> tuple[int, str]:
    with all_tenants():
        driver = db.session.scalars(
            select(Driver).where(Driver.tenant_id == demo["tenants"][RED_DRAW]).order_by(Driver.id)
        ).first()
        return driver.id, driver.full_name


def _packet_entries() -> list[AuditLog]:
    with all_tenants():
        return list(db.session.scalars(select(AuditLog).where(AuditLog.action == "packet")))


# --- the page -------------------------------------------------------------------


def test_packet_shows_every_section_an_auditor_asks_for(demo, demo_login):
    driver_id, name = _red_draw_driver(demo)
    html = demo_login("owner@demo.example").get(f"/drivers/{driver_id}/packet")
    assert html.status_code == 200
    text = html.get_data(as_text=True)
    for heading in (
        "Driver qualification file · Audit packet",
        name,
        RED_DRAW,
        "Compliance status",
        "Qualification summary",
        "Qualification file checklist",
        "Drug and alcohol tests",
        "Training",
        "Hours of service, last 7 days",
        "Reviewed by",
        "not regulatory advice",
        "Print or save as PDF",
    ):
        assert heading in text, heading


def test_packet_names_who_generated_it_when_and_its_audit_reference(demo, demo_login):
    driver_id, _ = _red_draw_driver(demo)
    text = demo_login("owner@demo.example").get(f"/drivers/{driver_id}/packet").get_data(True)
    (entry,) = _packet_entries()
    assert f"Audit log #{entry.id}" in text
    assert "Cal Brennan" in text  # the seeded Carrier Admin
    assert "US Central" in text


def test_driver_page_links_to_its_packet(demo, demo_login):
    driver_id, _ = _red_draw_driver(demo)
    html = demo_login("owner@demo.example").get(f"/drivers/{driver_id}").get_data(as_text=True)
    assert f'href="/drivers/{driver_id}/packet"' in html


# --- logging and permissions -----------------------------------------------------


def test_each_packet_is_logged_against_the_driver(demo, demo_login):
    driver_id, name = _red_draw_driver(demo)
    client = demo_login("owner@demo.example")
    client.get(f"/drivers/{driver_id}/packet")
    client.get(f"/drivers/{driver_id}/packet")
    entries = _packet_entries()
    assert len(entries) == 2
    for entry in entries:
        assert (entry.table_name, entry.record_id) == ("drivers", driver_id)
        assert entry.tenant_id == demo["tenants"][RED_DRAW]
        assert entry.user_id is not None
        assert entry.summary == f"Generated the audit packet for {name}"


def test_carrier_viewer_can_pull_a_packet(demo, demo_login):
    driver_id, _ = _red_draw_driver(demo)
    assert demo_login("viewer@demo.example").get(f"/drivers/{driver_id}/packet").status_code == 200


def test_users_without_driver_access_get_403_and_nothing_is_logged(demo, demo_login):
    driver_id, _ = _red_draw_driver(demo)
    shop = demo_login("shop@demo.example", demo["tenants"][RED_DRAW])  # maintenance only
    assert shop.get(f"/drivers/{driver_id}/packet").status_code == 403
    assert _packet_entries() == []


def test_another_carriers_driver_is_404_and_nothing_is_logged(demo, demo_login):
    with all_tenants():
        blue_stem_driver = db.session.scalar(
            select(func.min(Driver.id)).where(
                Driver.tenant_id == demo["tenants"]["Blue Stem Transport Inc."]
            )
        )
    client = demo_login("owner@demo.example")  # Red Draw only
    assert client.get(f"/drivers/{blue_stem_driver}/packet").status_code == 404
    assert _packet_entries() == []


# --- checklist status, unit level --------------------------------------------------


def _item(kind, completed_on=TODAY - timedelta(days=100), due_on=None):
    return SimpleNamespace(item_type=kind, completed_on=completed_on, due_on=due_on)


def test_file_rows_mark_missing_due_soon_overdue_and_current():
    driver = SimpleNamespace(
        file_items=[
            _item(FileItemType.MVR, due_on=TODAY + timedelta(days=12)),
            _item(FileItemType.ROAD_TEST),
            _item(FileItemType.ANNUAL_REVIEW, due_on=TODAY - timedelta(days=1)),
            _item(FileItemType.PREVIOUS_EMPLOYER_CHECK, completed_on=None),
        ]
    )
    rows = {row.label: row for row in file_rows(driver, TODAY)}
    assert (rows["Employment application"].level, rows["Employment application"].note) == (
        Level.RED,
        "Not on file",
    )
    assert rows["Previous employer check"].note == "Not on file"
    assert rows["Motor vehicle record (MVR)"].level == Level.YELLOW
    assert "in 12 days" in rows["Motor vehicle record (MVR)"].note
    assert rows["Annual review"].level == Level.RED
    assert rows["Annual review"].note.startswith("Overdue")
    assert (rows["Road test"].level, rows["Road test"].note) == (Level.GREEN, "On file")

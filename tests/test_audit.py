"""Audit log: automatic row-level entries, suppressed bulk jobs, and page visibility."""

from datetime import date

from sqlalchemy import select

from app.audit import audit_suppressed, record
from app.extensions import db
from app.models import AuditLog, Driver
from app.tenancy import all_tenants, tenant_scope


def _entries(**where):
    with all_tenants():
        stmt = select(AuditLog).order_by(AuditLog.id)
        for key, value in where.items():
            stmt = stmt.where(getattr(AuditLog, key) == value)
        return db.session.scalars(stmt).all()


def test_create_update_delete_are_audited(world):
    with tenant_scope(world["a"]):
        driver = Driver(first_name="Ana", last_name="Ruiz", cdl_number="TX-9")
        db.session.add(driver)
        db.session.commit()
        driver.medical_card_expiration = date(2027, 1, 31)
        db.session.commit()
        db.session.delete(driver)
        db.session.commit()

    entries = _entries(table_name="drivers", record_id=driver.id)
    assert [e.action for e in entries] == ["create", "update", "delete"]
    created, updated, deleted = entries
    assert created.after["cdl_number"] == "TX-9"
    assert updated.before == {"medical_card_expiration": None}
    assert updated.after == {"medical_card_expiration": "2027-01-31"}
    assert deleted.before["last_name"] == "Ruiz"
    assert {e.tenant_id for e in entries} == {world["a"]}


def test_no_op_update_is_not_audited(world):
    with tenant_scope(world["a"]):
        driver = db.session.scalars(select(Driver)).one()
        driver.first_name = driver.first_name
        db.session.commit()
    assert _entries(action="update") == []


def test_suppressed_block_writes_only_summary(world):
    with tenant_scope(world["a"]), audit_suppressed():
        driver = Driver(first_name="Bulk", last_name="One", cdl_number="B-1")
        db.session.add(driver)
        record("import", "Imported 1 driver")
        db.session.commit()
    assert _entries(table_name="drivers", record_id=driver.id) == []
    assert _entries(action="import")[0].summary == "Imported 1 driver"


def test_edits_through_the_app_record_the_user(login, world):
    client = login("carrier_admin")
    client.get("/")  # request context with a logged-in user
    with client.application.test_request_context():
        from flask_login import login_user

        from app.models import User

        user = db.session.scalars(select(User).where(User.email == "owner@test.example")).one()
        login_user(user)
        with tenant_scope(world["a"]):
            db.session.add(Driver(first_name="Who", last_name="Did", cdl_number="W-1"))
            db.session.commit()
    entry = _entries(action="create", table_name="drivers")[-1]
    assert entry.user_id == world["users"]["carrier_admin"]


def test_audit_page_visibility(login, world):
    assert login("viewer").get("/audit/").status_code == 403
    assert login("shop").get("/audit/").status_code == 403
    assert login("carrier_admin").get("/audit/").status_code == 200
    assert login("provider_admin").get("/audit/").status_code == 200


def test_carrier_admin_sees_only_own_tenant_entries(login, world):
    with all_tenants():
        record("note", "secret B entry", tenant_id=world["b"])
        record("note", "visible A entry", tenant_id=world["a"])
        db.session.commit()
    html = login("carrier_admin").get("/audit/").get_data(as_text=True)
    assert "visible A entry" in html
    assert "secret B entry" not in html
    # Filtering by B's tenant id is ignored for carrier users
    html = login("carrier_admin").get(f"/audit/?tenant_id={world['b']}").get_data(as_text=True)
    assert "secret B entry" not in html


def test_provider_admin_sees_all_and_can_filter(login, world):
    with all_tenants():
        record("note", "entry for B", tenant_id=world["b"])
        record("note", "entry for A", tenant_id=world["a"])
        db.session.commit()
    client = login("provider_admin")
    html = client.get("/audit/?action=note").get_data(as_text=True)
    assert "entry for A" in html and "entry for B" in html
    html = client.get(f"/audit/?action=note&tenant_id={world['b']}").get_data(as_text=True)
    assert "entry for B" in html and "entry for A" not in html

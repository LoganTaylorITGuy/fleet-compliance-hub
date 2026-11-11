import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Driver, Role, User
from app.tenancy import tenant_scope

from .factories import make_provider, make_tenant


def test_carrier_user_requires_tenant(app):
    provider = make_provider()
    db.session.add(
        User(email="x@example.com", name="X", password_hash="x", role=Role.CARRIER_ADMIN)
    )
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
    db.session.add(
        User(
            email="p@example.com",
            name="P",
            password_hash="x",
            role=Role.PROVIDER_ADMIN,
            provider_id=provider.id,
        )
    )
    db.session.flush()


def test_cdl_number_unique_per_tenant_only(app):
    provider = make_provider()
    a, b = make_tenant(provider, "A"), make_tenant(provider, "B")
    for tenant in (a, b):
        with tenant_scope(tenant.id):
            db.session.add(Driver(first_name="Sam", last_name="Lee", cdl_number="TX123"))
            db.session.commit()
    with tenant_scope(a.id):
        db.session.add(Driver(first_name="Dup", last_name="Lee", cdl_number="TX123"))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_driver_full_name():
    assert Driver(first_name="Ana", last_name="Ruiz").full_name == "Ana Ruiz"

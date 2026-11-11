import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Role

from .factories import DEMO_PASSWORD, make_provider, make_tenant, make_user, populate_tenant


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def world(app):
    """A provider with two carriers (A and B), sample data and one user per role."""
    provider = make_provider()
    other_provider = make_provider("Someone Else Compliance")
    a = make_tenant(provider, "Carrier A")
    b = make_tenant(provider, "Carrier B")
    stranger = make_tenant(other_provider, "Other Provider's Carrier")
    rows_a = {k: v.id for k, v in populate_tenant(a, "A").items()}
    rows_b = {k: v.id for k, v in populate_tenant(b, "B").items()}
    users = {
        "provider_admin": make_user("admin@test.example", Role.PROVIDER_ADMIN, provider=provider),
        "shop": make_user(
            "shop@test.example", Role.PROVIDER_LIMITED, provider=provider, permissions="maintenance"
        ),
        "carrier_admin": make_user("owner@test.example", Role.CARRIER_ADMIN, tenant=a),
        "viewer": make_user("viewer@test.example", Role.CARRIER_VIEWER, tenant=a),
        "b_admin": make_user("b-owner@test.example", Role.CARRIER_ADMIN, tenant=b),
    }
    ids = {
        "provider": provider.id,
        "a": a.id,
        "b": b.id,
        "stranger": stranger.id,
        "rows_a": rows_a,
        "rows_b": rows_b,
        "users": {k: u.id for k, u in users.items()},
        "emails": {k: u.email for k, u in users.items()},
    }
    db.session.expunge_all()
    return ids


@pytest.fixture
def login(client, world):
    """login("carrier_admin") logs the test client in as that world user."""

    def _login(who: str, tenant: str | None = None):
        client.post("/logout")
        response = client.post(
            "/login", data={"email": world["emails"][who], "password": DEMO_PASSWORD}
        )
        assert response.status_code == 302, f"login failed for {who}"
        if tenant:
            client.post("/switch-tenant", data={"tenant_id": world[tenant]})
        return client

    return _login

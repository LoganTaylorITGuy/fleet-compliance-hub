import pytest
from sqlalchemy import select

from app import create_app
from app.auth.services import safe_next_url
from app.config import TestConfig
from app.extensions import db
from app.models import AuditLog, Role
from app.permissions import can_edit, can_view
from app.tenancy import all_tenants

from .factories import DEMO_PASSWORD, make_provider, make_user


def test_pages_require_login(client, world):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_healthz_is_public(client):
    assert client.get("/healthz").status_code == 200


def test_login_success_and_logout(client, world):
    response = client.post(
        "/login", data={"email": "OWNER@test.example ", "password": DEMO_PASSWORD}
    )
    assert response.status_code == 302
    assert "Carrier A" in client.get("/").get_data(as_text=True)
    client.post("/logout")
    assert client.get("/").status_code == 302


@pytest.mark.parametrize(
    ("email", "password"),
    [("owner@test.example", "wrong"), ("nobody@test.example", DEMO_PASSWORD)],
)
def test_login_failure_is_generic(client, world, email, password):
    response = client.post("/login", data={"email": email, "password": password})
    assert response.status_code == 200
    assert "don&#39;t match an active account" in response.get_data(as_text=True)


def test_inactive_user_cannot_log_in(client, app):
    provider = make_provider()
    make_user("gone@test.example", Role.PROVIDER_ADMIN, provider=provider, active=False)
    response = client.post("/login", data={"email": "gone@test.example", "password": DEMO_PASSWORD})
    assert response.status_code == 200


def test_login_is_audited(client, world):
    client.post("/login", data={"email": "owner@test.example", "password": DEMO_PASSWORD})
    with all_tenants():
        entry = db.session.scalars(select(AuditLog).where(AuditLog.action == "login")).one()
    assert entry.user_id == world["users"]["carrier_admin"]
    assert entry.tenant_id == world["a"]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/drivers", "/drivers"),
        ("https://evil.example/", None),
        ("//evil.example", None),
        ("drivers", None),
        ("", None),
    ],
)
def test_safe_next_url(target, expected):
    assert safe_next_url(target) == expected


def test_demo_switcher_shown_and_works_in_demo_mode(client, world, monkeypatch):
    from app.auth import services

    monkeypatch.setitem(
        services.DEMO_PERSONAS, "carrier_viewer", ("viewer@test.example", "Viewer", "")
    )
    html = client.get("/login").get_data(as_text=True)
    assert "Demo logins" in html
    response = client.post("/login/demo", data={"persona": "carrier_viewer"})
    assert response.status_code == 302
    assert "Viewer" in client.get("/").get_data(as_text=True)


def test_demo_switcher_unknown_persona(client, world):
    assert client.post("/login/demo", data={"persona": "root"}).status_code == 400


def test_demo_switcher_disabled_outside_demo_mode(world):
    app = create_app(TestConfig, DEMO_MODE=False)
    client = app.test_client()
    with app.app_context():
        assert "Demo logins" not in client.get("/login").get_data(as_text=True)
        assert client.post("/login/demo", data={"persona": "provider_admin"}).status_code == 404


def test_csrf_enforced_when_enabled(world):
    app = create_app(TestConfig, WTF_CSRF_ENABLED=True)
    client = app.test_client()
    with app.app_context():
        response = client.post(
            "/login", data={"email": "owner@test.example", "password": DEMO_PASSWORD}
        )
    assert response.status_code == 400  # rejected: no CSRF token


def test_provider_switches_tenant(login, world):
    client = login("provider_admin")
    assert "Choose a carrier" in client.get("/").get_data(as_text=True)
    client.post("/switch-tenant", data={"tenant_id": world["b"]})
    assert "Carrier B" in client.get("/").get_data(as_text=True)


def test_provider_cannot_switch_to_another_providers_tenant(login, world):
    client = login("provider_admin")
    response = client.post("/switch-tenant", data={"tenant_id": world["stranger"]})
    assert response.status_code == 404


def test_carrier_cannot_switch_tenant(login, world):
    client = login("carrier_admin")
    assert client.post("/switch-tenant", data={"tenant_id": world["b"]}).status_code == 403
    assert "Carrier A" in client.get("/").get_data(as_text=True)


def test_logout_requires_post(login):
    client = login("carrier_admin")
    assert client.get("/logout").status_code == 405


class _FakeUser:
    is_authenticated = True

    def __init__(self, role, permissions=""):
        self.role = role
        self.permissions = permissions


@pytest.mark.parametrize(
    ("role", "permissions", "area", "view", "edit"),
    [
        (Role.PROVIDER_ADMIN, "", "audit", True, True),
        (Role.CARRIER_ADMIN, "", "imports", True, True),
        (Role.CARRIER_VIEWER, "", "drivers", True, False),
        (Role.CARRIER_VIEWER, "", "audit", False, False),
        (Role.CARRIER_VIEWER, "", "imports", False, False),
        (Role.PROVIDER_LIMITED, "maintenance", "maintenance", True, True),
        (Role.PROVIDER_LIMITED, "maintenance", "fleet", True, False),
        (Role.PROVIDER_LIMITED, "maintenance", "drivers", False, False),
        (Role.PROVIDER_LIMITED, "training", "drivers", True, False),
        (Role.PROVIDER_LIMITED, "training", "training", True, True),
        (Role.PROVIDER_LIMITED, "training", "audit", False, False),
        (Role.PROVIDER_LIMITED, "bogus", "dashboard", True, False),
    ],
)
def test_permission_matrix(role, permissions, area, view, edit):
    user = _FakeUser(role, permissions)
    assert can_view(user, area) is view
    assert can_edit(user, area) is edit

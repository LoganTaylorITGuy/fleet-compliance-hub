import pytest

from app import create_app
from app.config import (
    Config,
    TestConfig,
    env_bool,
    env_str,
    normalize_database_url,
    resolve_secret_key,
)


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_layout_has_disclaimer_and_skip_link(client):
    html = client.get("/").get_data(as_text=True)
    assert "Demo only. Not legal or regulatory advice. Rules simplified for illustration." in html
    assert 'href="#main"' in html
    assert 'lang="en"' in html


def test_unknown_page_is_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "couldn" in response.get_data(as_text=True)


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]


def test_provider_name_is_configurable():
    app = create_app(TestConfig, PROVIDER_NAME="Example Compliance LLC")
    html = app.test_client().get("/").get_data(as_text=True)
    assert "Example Compliance LLC" in html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_secret_key_required_outside_local():
    with pytest.raises(RuntimeError):
        resolve_secret_key({"APP_ENV": "production", "SECRET_KEY": None})
    assert len(resolve_secret_key({"APP_ENV": "local", "SECRET_KEY": None})) == 64
    assert resolve_secret_key({"APP_ENV": "production", "SECRET_KEY": "abc"}) == "abc"


def test_demo_mode_refused_in_production():
    with pytest.raises(RuntimeError):
        create_app(Config, APP_ENV="production", SECRET_KEY="x", DEMO_MODE=True)


def test_blank_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    monkeypatch.setenv("DEMO_MODE", "yes")
    assert env_str("DATABASE_URL", "sqlite://") == "sqlite://"
    assert env_bool("DEMO_MODE") is True
    assert env_bool("UNSET_FLAG_FOR_TEST", default=True) is True

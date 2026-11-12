"""Home: where every user lands after signing in."""

import re
from datetime import datetime

import pytest

from app.formatting import LOCAL_TZ

RED_DRAW = "Red Draw Hauling Co."


@pytest.fixture
def home(client, demo, demo_login, monkeypatch):
    """home("owner@demo.example") -> the Home page HTML at 09:00 on the demo date."""
    moment = datetime.combine(demo["today"], datetime.min.time(), LOCAL_TZ).replace(hour=9)
    monkeypatch.setattr("app.clock.now", lambda: moment)

    def _home(email, tenant=None):
        demo_login(email, demo["tenants"][tenant] if tenant else None)
        response = client.get("/")
        assert response.status_code == 200
        return response.get_data(as_text=True)

    return _home


def tile_labels(html):
    nav = html[html.index('id="tiles-heading"') : html.index("</nav>", html.index("tiles-heading"))]
    return re.findall(r'<span class="mt-3 font-semibold[^"]*">([^<]+)</span>', nav)


def test_login_lands_on_home(client, demo):
    from .factories import DEMO_PASSWORD

    response = client.post(
        "/login", data={"email": "owner@demo.example", "password": DEMO_PASSWORD}
    )
    assert response.headers["Location"] == "/"


def test_greets_by_first_name_and_time_of_day(home):
    html = home("owner@demo.example")
    assert "Good morning, Cal" in html
    assert "Tuesday, November 17" in html


def test_carrier_sees_its_glance_and_tiles(home):
    html = home("owner@demo.example")
    assert "At a glance" in html
    assert "Your carriers" not in html
    assert RED_DRAW in html
    assert tile_labels(html) == [
        "Dashboard", "Drivers", "Fleet", "Hours of Service", "Training",
        "Import", "Integrations", "Audit log",
    ]  # fmt: skip


def test_tiles_follow_role_permissions(home):
    labels = tile_labels(home("viewer@demo.example"))
    assert "Import" not in labels
    assert "Integrations" not in labels
    assert "Audit log" not in labels
    assert "Drivers" in labels


def test_provider_without_carrier_sees_ranked_carriers(home):
    html = home("admin@demo.example")
    assert "Your carriers" in html
    assert "At a glance" not in html
    section = html[html.index("Your carriers") : html.index('id="tiles-heading"')]
    order = [
        section.index(n) for n in ("Blue Stem Transport Inc.", RED_DRAW, "Cedar Mesa Freight LLC")
    ]
    assert order == sorted(order)
    assert 'action="/switch-tenant"' in section
    assert tile_labels(html)[0] == "Carrier clients"
    assert "Drivers" not in tile_labels(html)  # needs a carrier first


def test_provider_with_carrier_sees_that_carrier(home):
    html = home("admin@demo.example", tenant=RED_DRAW)
    assert "At a glance" in html
    assert f"· {RED_DRAW}" in html


def test_red_counts_badge_the_matching_tiles(home):
    html = home("owner@demo.example")
    badges = re.findall(r'(\d+)<span class="sr-only"> need action</span>', html)
    assert badges and all(int(n) > 0 for n in badges)


def test_home_is_not_recorded_as_a_recent_page(home):
    assert "data-recent-title" not in home("owner@demo.example")


def test_home_is_in_the_menu_for_everyone(home):
    for email in ("owner@demo.example", "viewer@demo.example", "shop@demo.example"):
        assert 'href="/"' in home(email)

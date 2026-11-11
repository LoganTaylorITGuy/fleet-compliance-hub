"""Global search endpoint and the page shell (header, bottom bar, overlays, theme)."""

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Driver, Vehicle
from app.tenancy import all_tenants

RED_DRAW = "Red Draw Hauling Co."
BLUE_STEM = "Blue Stem Transport Inc."


def _first(model, tenant_id):
    with all_tenants():
        obj = db.session.scalars(
            select(model).where(model.tenant_id == tenant_id).order_by(model.id)
        ).first()
        db.session.expunge(obj)
        return obj


def test_search_finds_drivers_and_units(demo, demo_login):
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    client = demo_login("owner@demo.example")
    results = client.get(f"/search/?q={driver.last_name}").get_json()["results"]
    assert any(r["title"] == driver.full_name and r["kind"] == "Driver" for r in results)
    units = client.get("/search/?q=TR50").get_json()["results"]
    assert units and all(r["kind"] == "Unit" for r in units)
    assert (
        client.get(f"/search/?q={driver.cdl_number}")
        .get_json()["results"][0]["url"]
        .endswith(f"/drivers/{driver.id}")
    )


@pytest.mark.isolation
def test_search_never_returns_other_carriers(demo, demo_login):
    other = _first(Driver, demo["tenants"][BLUE_STEM])
    client = demo_login("owner@demo.example")
    results = client.get(f"/search/?q={other.cdl_number}").get_json()["results"]
    assert results == []


def test_search_needs_two_characters_and_a_carrier(demo, demo_login):
    client = demo_login("owner@demo.example")
    assert client.get("/search/?q=a").get_json()["results"] == []
    provider = demo_login("admin@demo.example")  # no carrier chosen yet
    assert provider.get("/search/?q=Unit").get_json()["results"] == []


def test_search_requires_login(client, demo):
    assert client.get("/search/?q=TR").status_code == 302


def test_search_respects_permissions(demo, demo_login):
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    shop = demo_login("shop@demo.example", demo["tenants"][RED_DRAW])
    assert shop.get(f"/search/?q={driver.cdl_number}").get_json()["results"] == []
    vehicle = _first(Vehicle, demo["tenants"][RED_DRAW])
    assert shop.get(f"/search/?q={vehicle.unit_number}").get_json()["results"]


def test_shell_on_every_signed_in_page(demo, demo_login):
    client = demo_login("owner@demo.example")
    for path in (
        "/dashboard/",
        "/drivers/",
        "/fleet/",
        "/hours/",
        "/training/",
        "/import/",
        "/integrations/",
        "/audit/",
        "/no-such-page",
    ):
        html = client.get(path).get_data(as_text=True)
        assert 'id="global-search"' in html, path
        assert 'data-open-dialog="nav-overlay"' in html, path
        assert "data-theme-toggle" in html, path
        assert 'id="help-dialog"' in html, path


def test_login_page_has_header_but_no_bottom_bar(client, demo):
    html = client.get("/login").get_data(as_text=True)
    assert "data-theme-toggle" in html and 'id="help-dialog"' in html
    assert 'id="global-search"' not in html


def test_menu_lists_only_permitted_pages(demo, demo_login):
    html = demo_login("viewer@demo.example").get("/dashboard/").get_data(as_text=True)
    assert "Hours of Service" in html
    assert "/import/" not in html and "/audit/" not in html


def test_theme_script_loads_before_styles(client, demo):
    html = client.get("/login").get_data(as_text=True)
    assert html.index("js/theme.js") < html.index("css/app.css")
    assert 'theme.js"></script>' in html  # not deferred: avoids a flash of the wrong theme


def test_recents_metadata(demo, demo_login):
    driver = _first(Driver, demo["tenants"][RED_DRAW])
    client = demo_login("owner@demo.example")
    html = client.get(f"/drivers/{driver.id}").get_data(as_text=True)
    assert f'data-recent-title="{driver.full_name}" data-recent-kind="Driver"' in html
    assert f'data-tenant="{demo["tenants"][RED_DRAW]}"' in html  # recents are kept per carrier
    assert "data-recent-title" not in client.get("/no-such-page").get_data(as_text=True)


def test_page_suggestions_carry_keywords(demo, demo_login):
    html = demo_login("owner@demo.example").get("/dashboard/").get_data(as_text=True)
    assert 'data-label="fleet"' in html
    assert "dvir" in html.split('data-label="fleet"')[1].split(">")[0]

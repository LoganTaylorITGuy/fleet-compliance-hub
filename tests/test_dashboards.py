"""Provider and carrier dashboards: ranking, planted items, and who can see what."""

import re
from datetime import date, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import Driver
from app.tenancy import all_tenants

from .factories import DEMO_PASSWORD


def login(client, email):
    client.post("/logout")
    response = client.post("/login", data={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 302
    return client


def test_provider_lands_on_provider_dashboard(client, demo):
    login(client, "admin@demo.example")
    response = client.get("/")
    assert response.headers["Location"].endswith("/dashboard/provider")


def test_provider_dashboard_ranks_carriers_by_urgency(client, demo):
    html = login(client, "admin@demo.example").get("/dashboard/provider").get_data(as_text=True)
    table = html[html.index("<tbody") :]  # the sidebar switcher lists carriers A to Z
    order = [
        table.index(name)
        for name in (
            "Blue Stem Transport Inc.",
            "Red Draw Hauling Co.",
            "Cedar Mesa Freight LLC",
            "High Plains Driving Academy",
        )
    ]
    assert order == sorted(order)
    assert "action needed" in html  # screen-reader text on the count pills


def test_open_carrier_from_provider_dashboard(client, demo):
    login(client, "admin@demo.example")
    response = client.post(
        "/switch-tenant",
        data={"tenant_id": demo["tenants"]["Red Draw Hauling Co."], "next": "/dashboard/"},
    )
    assert response.headers["Location"].endswith("/dashboard/")
    html = client.get("/dashboard/").get_data(as_text=True)
    assert "Red Draw Hauling Co." in html
    assert "Needs action now" in html


def test_carrier_name_is_the_click_target(client, demo):
    """Each carrier's name submits that row's open-carrier form (no off-screen button)."""
    html = login(client, "admin@demo.example").get("/dashboard/provider").get_data(as_text=True)
    table = html[html.index("<tbody") : html.index("</tbody>")]
    forms = re.findall(r"<form .*?</form>", table, flags=re.S)
    assert len(forms) == len(demo["tenants"])
    for name, tenant_id in demo["tenants"].items():
        form = next(f for f in forms if f'name="tenant_id" value="{tenant_id}"' in f)
        assert 'action="/switch-tenant"' in form  # a POST (CSRF tested in test_auth.py)
        button = re.search(r"<button[^>]*>(.*?)</button>", form, flags=re.S)
        assert button.group(1).strip() == name
        assert "after:inset-0" in button.group(0)  # stretched over the whole row
    assert ">Open<" not in table


def test_carrier_dashboard_shows_planted_items(client, demo):
    html = login(client, "owner@demo.example").get("/dashboard/").get_data(as_text=True)
    assert "Expiring in 30 days" in html
    assert "in 12 days" in html  # the planted medical card
    assert "11-hour driving limit exceeded" in html  # the planted HOS violation
    assert "Air leak at gladhand" in html  # the planted open DVIR defect
    assert "Action needed" in html and "Current" in html  # text, not just color


def test_carrier_dashboard_shows_only_own_carrier(client, demo):
    with all_tenants():
        other = db.session.scalars(
            select(Driver).where(Driver.tenant_id == demo["tenants"]["Blue Stem Transport Inc."])
        ).first()
        other_name = other.full_name
    html = login(client, "viewer@demo.example").get("/dashboard/").get_data(as_text=True)
    assert "Red Draw Hauling Co." in html
    assert "Blue Stem Transport Inc." not in html
    assert other_name not in html


def test_carrier_users_cannot_open_provider_dashboard(client, demo):
    assert login(client, "owner@demo.example").get("/dashboard/provider").status_code == 403
    assert login(client, "viewer@demo.example").get("/dashboard/provider").status_code == 403


def test_provider_without_carrier_is_sent_to_pick_one(client, demo):
    login(client, "admin@demo.example")
    response = client.get("/dashboard/")
    assert response.headers["Location"].endswith("/dashboard/provider")


def test_shop_user_can_see_dashboards(client, demo):
    login(client, "shop@demo.example")
    assert client.get("/dashboard/provider").status_code == 200


def test_expiring_list_is_sorted_by_due_date(client, demo):
    html = login(client, "owner@demo.example").get("/dashboard/").get_data(as_text=True)
    section = html[html.index("Expiring in 30 days") : html.index('id="drivers-heading"')]
    dates = [date.fromisoformat(m) for m in re.findall(r"\((\d{4}-\d{2}-\d{2})\)", section)]
    assert dates and dates == sorted(dates)
    assert all(d <= demo["today"] + timedelta(days=30) for d in dates)

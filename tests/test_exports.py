"""Excel export: every dataset, tenant scoping, formula-injection escaping, permissions."""

import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.exports import DATASETS, safe_cell
from app.extensions import db
from app.models import Driver
from app.tenancy import all_tenants, tenant_scope


def _sheet(response):
    assert response.status_code == 200
    assert response.mimetype.endswith("spreadsheetml.sheet")
    workbook = load_workbook(io.BytesIO(response.data))
    return workbook.active


@pytest.mark.parametrize("dataset", list(DATASETS))
def test_every_dataset_exports(demo, demo_login, dataset):
    response = demo_login("owner@demo.example").get(f"/export/{dataset}.xlsx")
    sheet = _sheet(response)
    assert sheet.max_row > 1
    assert "red-draw-hauling-co" in response.headers["Content-Disposition"]


@pytest.mark.isolation
def test_export_contains_only_own_tenant(demo, demo_login):
    blue = demo["tenants"]["Blue Stem Transport Inc."]
    red = demo["tenants"]["Red Draw Hauling Co."]
    with all_tenants():
        blue_cdls = set(
            db.session.scalars(select(Driver.cdl_number).where(Driver.tenant_id == blue))
        )
        red_cdls = set(db.session.scalars(select(Driver.cdl_number).where(Driver.tenant_id == red)))
    sheet = _sheet(demo_login("viewer@demo.example").get("/export/drivers.xlsx"))
    exported = {row[2] for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert exported == red_cdls
    assert not exported & blue_cdls


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("http://evil")', '\'=HYPERLINK("http://evil")'),
        ("+1+1", "'+1+1"),
        ("-2", "'-2"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("Ana", "Ana"),
        (5, 5),
    ],
)
def test_safe_cell(value, expected):
    assert safe_cell(value) == expected


def test_formula_in_data_is_exported_as_text(demo, demo_login):
    red = demo["tenants"]["Red Draw Hauling Co."]
    with tenant_scope(red):
        db.session.add(
            Driver(
                first_name='=HYPERLINK("http://evil.example")', last_name="Aaron", cdl_number="99X"
            )
        )
        db.session.commit()
    sheet = _sheet(demo_login("owner@demo.example").get("/export/drivers.xlsx"))
    first_names = [row[1] for row in sheet.iter_rows(min_row=2, values_only=True)]
    assert '\'=HYPERLINK("http://evil.example")' in first_names
    assert all(cell.data_type != "f" for row in sheet.iter_rows() for cell in row)


def test_export_permissions(demo, demo_login):
    viewer = demo_login("viewer@demo.example")
    assert viewer.get("/export/audit.xlsx").status_code == 403
    assert viewer.get("/export/nope.xlsx").status_code == 404
    shop = demo_login("shop@demo.example", demo["tenants"]["Red Draw Hauling Co."])
    assert shop.get("/export/fleet.xlsx").status_code == 200
    assert shop.get("/export/drivers.xlsx").status_code == 403


def test_provider_needs_a_carrier_to_export(demo, demo_login):
    response = demo_login("admin@demo.example").get("/export/drivers.xlsx")
    assert response.status_code == 302

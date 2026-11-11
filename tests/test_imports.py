"""Spreadsheet import: parsing, mapping, validation, the full web flow, and undo."""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.imports import engine
from app.imports.parsing import ImportFileError, parse_bool, parse_date, read_table
from app.imports.specs import SPECS, suggest_mapping
from app.models import AuditLog, Driver, ImportRun, ImportTemplate, Vehicle
from app.tenancy import all_tenants, tenant_scope

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
RED_DRAW = "Red Draw Hauling Co."
BLUE_STEM = "Blue Stem Transport Inc."


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "2027-03-14",
        "03/14/2027",
        "3/14/27",
        "14-Mar-2027",
        "March 14, 2027",
        "Mar 14 2027",
        "2027-03-14 00:00:00",
        "46460",  # Excel serial day number
    ],
)
def test_parse_date_formats(text):
    assert parse_date(text) == date(2027, 3, 14)


@pytest.mark.parametrize("text", ["soon", "13/45/2026", "2026", ""])
def test_parse_date_rejects_garbage(text):
    with pytest.raises(ValueError, match="isn't a date"):
        parse_date(text)


def test_parse_bool():
    assert parse_bool("Yes") is True and parse_bool("x") is True
    assert parse_bool("no") is False and parse_bool("") is False
    with pytest.raises(ValueError):
        parse_bool("maybe")


def test_read_table_csv_and_xlsx():
    headers, rows = read_table("v.csv", (SAMPLES / "vehicles_messy.csv").read_bytes())
    assert headers[0] == "Unit #" and len(rows) == 6
    headers, rows = read_table("d.xlsx", (SAMPLES / "drivers_messy.xlsx").read_bytes())
    assert headers[:2] == ["Driver Name", "CDL #"] and len(rows) == 8
    assert all(isinstance(cell, str) for row in rows for cell in row)


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("evil.exe", b"MZ", "Upload an Excel"),
        ("bad.xlsx", b"not really excel", "couldn't be read"),
        ("empty.csv", b"a,b\n", "no data rows"),
    ],
)
def test_read_table_rejects_bad_files(name, data, message):
    with pytest.raises(ImportFileError, match=message):
        read_table(name, data)


def test_read_table_row_limit(monkeypatch):
    monkeypatch.setattr("app.imports.parsing.MAX_ROWS", 2)
    with pytest.raises(ImportFileError, match="limited"):
        read_table("x.csv", b"a\n1\n2\n3\n")


# --- mapping suggestions -------------------------------------------------------


def test_suggest_mapping_for_messy_driver_headers():
    headers, _ = read_table("d.xlsx", (SAMPLES / "drivers_messy.xlsx").read_bytes())
    mapping = suggest_mapping(SPECS["drivers"], headers)
    assert mapping == {
        "Driver Name": "full_name",
        "CDL #": "cdl_number",
        "Lic State": "cdl_state",
        "Class": "cdl_class",
        "CDL Exp.": "cdl_expiration",
        "DOT Physical Exp": "medical_card_expiration",
        "Date Hired": "hire_date",
        "Cell": "phone",
        "Notes": "",
    }


def test_suggest_mapping_never_reuses_a_field():
    mapping = suggest_mapping(SPECS["vehicles"], ["Unit", "Unit No", "Type"])
    targets = [t for t in mapping.values() if t]
    assert len(targets) == len(set(targets))


# --- engine ----------------------------------------------------------------------


def _driver_rows(demo):
    headers, rows = read_table("d.xlsx", (SAMPLES / "drivers_messy.xlsx").read_bytes())
    mapping = suggest_mapping(SPECS["drivers"], headers)
    with tenant_scope(demo["tenants"][RED_DRAW]):
        return engine.build_rows(SPECS["drivers"], headers, rows, mapping)


def test_engine_flags_the_planted_problems(demo):
    results = _driver_rows(demo)
    errors = {r.line: r.errors for r in results if r.errors}
    assert set(errors) == {5, 6, 7}
    assert "Duplicate of line 4" in errors[5]["cdl_number"]
    assert errors[6]["cdl_number"] == "CDL number is required"
    assert "isn't a date" in errors[7]["medical_card_expiration"]


def test_engine_splits_names_and_normalizes_cdl(demo):
    ana = _driver_rows(demo)[1]
    assert (ana.values["first_name"], ana.values["last_name"]) == ("Ana", "Ruiz")
    assert ana.values["cdl_number"] == "99451180"
    assert ana.values["cdl_state"] == "tx"


def test_choice_fields_accept_synonyms_and_reject_unknowns(demo):
    headers, rows = read_table("v.csv", (SAMPLES / "vehicles_messy.csv").read_bytes())
    mapping = suggest_mapping(SPECS["vehicles"], headers)
    with tenant_scope(demo["tenants"][RED_DRAW]):
        results = engine.build_rows(SPECS["vehicles"], headers, rows, mapping)
    types = [r.values.get("vehicle_type") for r in results]
    assert types[:4] == ["tractor", "tractor", "trailer", "trailer"]
    assert "isn't a valid type" in results[5].errors["vehicle_type"]
    assert "Duplicate of line 5" in results[4].errors["unit_number"]


# --- the web flow (demo step 7) --------------------------------------------------


def _upload(client, filename, data_type, template_id=None):
    data = {
        "data_type": data_type,
        "file": (io.BytesIO((SAMPLES / filename).read_bytes()), filename),
    }
    if template_id:
        data["template_id"] = str(template_id)
    response = client.post("/import/", data=data, content_type="multipart/form-data")
    assert response.status_code == 302, response.get_data(as_text=True)[:300]
    match = re.search(r"/import/([\w-]+)/map", response.headers["Location"])
    assert match, response.headers["Location"]
    return match.group(1)


def _mapping_form(client, token):
    html = client.get(f"/import/{token}/map").get_data(as_text=True)
    form = {}
    for select_html in re.findall(r'<select id="(col_\d+)".*?</select>', html, re.S):
        block = re.search(rf'<select id="{select_html}".*?</select>', html, re.S).group(0)
        chosen = re.search(r'<option value="([^"]*)" selected', block)
        form[select_html] = chosen.group(1) if chosen else ""
    return form


def _count(model, tenant_id):
    with all_tenants():
        return db.session.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        )


def test_messy_driver_import_end_to_end_then_undo(demo, demo_login):
    red = demo["tenants"][RED_DRAW]
    client = demo_login("owner@demo.example")
    before = _count(Driver, red)

    token = _upload(client, "drivers_messy.xlsx", "drivers")
    mapping = _mapping_form(client, token)
    assert mapping["col_0"] == "full_name"

    review = client.post(
        f"/import/{token}/map", data={**mapping, "template_name": "Monthly roster"}
    )
    assert review.headers["Location"].endswith(f"/import/{token}/review")
    html = client.get(f"/import/{token}/review").get_data(as_text=True)
    assert "3 rows need attention" in html
    assert "disabled" in html  # import blocked until fixed

    # Importing with errors is refused.
    client.post(f"/import/{token}/review", data={"action": "import"})
    assert _count(Driver, red) == before

    # Fix the bad date on line 7 (index 5), skip the duplicate and the blank CDL.
    fix = {
        "action": "recheck",
        "fix_5_full_name": "Jo Fenner",
        "fix_5_cdl_number": "99442210",
        "fix_5_medical_card_expiration": "12/31/2027",
        "skip_3": "1",
        "skip_4": "1",
    }
    html = client.post(f"/import/{token}/review", data=fix).get_data(as_text=True)
    assert "need attention" not in html
    assert "Import 6 rows" in html

    done = client.post(
        f"/import/{token}/review", data={**fix, "action": "import"}, follow_redirects=True
    )
    assert "6 added, 0 updated, 2 skipped" in done.get_data(as_text=True)
    assert _count(Driver, red) == before + 6

    with all_tenants():
        jo = db.session.scalars(select(Driver).where(Driver.cdl_number == "99442210")).one()
        assert jo.medical_card_expiration == date(2027, 12, 31)
        assert jo.tenant_id == red
        run = db.session.scalars(select(ImportRun).where(ImportRun.tenant_id == red)).one()
        assert run.rows_added == 6
        summary = db.session.scalars(select(AuditLog).where(AuditLog.action == "import")).one()
        assert "6 added" in summary.summary
        # Row-level audit entries were suppressed in favor of the summary.
        assert not db.session.scalars(
            select(AuditLog).where(AuditLog.table_name == "drivers", AuditLog.record_id == jo.id)
        ).all()

    # The dashboard picks up the new drivers.
    dash = client.get("/dashboard/").get_data(as_text=True)
    assert "Della Price" in dash

    # The staged upload is gone once committed.
    assert client.get(f"/import/{token}/review").status_code == 404

    # Undo the import.
    undo = client.post(f"/import/runs/{run.id}/undo", follow_redirects=True)
    assert "6 removed, 0 restored" in undo.get_data(as_text=True)
    assert _count(Driver, red) == before


def test_saved_template_prefills_next_month(demo, demo_login):
    client = demo_login("owner@demo.example")
    token = _upload(client, "drivers_messy.xlsx", "drivers")
    mapping = _mapping_form(client, token)
    mapping["col_8"] = "phone"  # deliberately odd choice: Notes -> phone
    mapping["col_7"] = ""
    client.post(f"/import/{token}/map", data={**mapping, "template_name": "Odd"})
    with all_tenants():
        template = db.session.scalars(select(ImportTemplate)).one()
    assert template.column_mapping["Notes"] == "phone"
    token2 = _upload(client, "drivers_messy.xlsx", "drivers", template_id=template.id)
    assert _mapping_form(client, token2)["col_8"] == "phone"


def test_vehicle_import_updates_existing_and_undo_restores(demo, demo_login, tmp_path):
    red = demo["tenants"][RED_DRAW]
    with all_tenants():
        unit = db.session.scalars(
            select(Vehicle).where(Vehicle.tenant_id == red).order_by(Vehicle.id)
        ).first()
        old_plate, unit_number = unit.plate, unit.unit_number
    csv_bytes = f"Unit #,Type,Tag\n{unit_number},Truck,NEW-PLATE\n".encode()
    client = demo_login("owner@demo.example")
    response = client.post(
        "/import/",
        data={"data_type": "vehicles", "file": (io.BytesIO(csv_bytes), "update.csv")},
        content_type="multipart/form-data",
    )
    token = re.search(r"/import/([\w-]+)/map", response.headers["Location"]).group(1)
    client.post(f"/import/{token}/map", data=_mapping_form(client, token))
    html = client.get(f"/import/{token}/review").get_data(as_text=True)
    assert "1 to update" in html
    client.post(f"/import/{token}/review", data={"action": "import"})
    with all_tenants():
        assert (
            db.session.scalars(
                select(Vehicle.plate).where(
                    Vehicle.unit_number == unit_number, Vehicle.tenant_id == red
                )
            ).one()
            == "NEW-PLATE"
        )
        run = db.session.scalars(select(ImportRun)).one()
    assert run.rows_updated == 1
    client.post(f"/import/runs/{run.id}/undo")
    with all_tenants():
        assert (
            db.session.scalars(
                select(Vehicle.plate).where(
                    Vehicle.unit_number == unit_number, Vehicle.tenant_id == red
                )
            ).one()
            == old_plate
        )


def test_only_latest_import_can_be_undone(demo, demo_login):
    client = demo_login("owner@demo.example")
    ids = []
    for n in (1, 2):
        csv_bytes = f"Driver Name,CDL #\nPat Number{n},9900000{n}\n".encode()
        response = client.post(
            "/import/",
            data={"data_type": "drivers", "file": (io.BytesIO(csv_bytes), f"d{n}.csv")},
            content_type="multipart/form-data",
        )
        token = re.search(r"/import/([\w-]+)/map", response.headers["Location"]).group(1)
        client.post(f"/import/{token}/map", data=_mapping_form(client, token))
        client.post(f"/import/{token}/review", data={"action": "import"})
        with all_tenants():
            ids.append(
                db.session.scalars(select(ImportRun.id).order_by(ImportRun.id.desc())).first()
            )
    first = client.post(f"/import/runs/{ids[0]}/undo", follow_redirects=True)
    assert "Only the most recent import" in first.get_data(as_text=True)


def test_mapping_same_field_twice_is_refused(demo, demo_login):
    client = demo_login("owner@demo.example")
    token = _upload(client, "drivers_messy.xlsx", "drivers")
    mapping = _mapping_form(client, token)
    mapping["col_8"] = "cdl_number"
    html = client.post(f"/import/{token}/map", data=mapping).get_data(as_text=True)
    assert "only come from one column" in html


def test_cancel_discards_upload(demo, demo_login):
    client = demo_login("owner@demo.example")
    token = _upload(client, "drivers_messy.xlsx", "drivers")
    client.post(f"/import/{token}/cancel")
    assert client.get(f"/import/{token}/map").status_code == 404


def test_bad_upload_shows_friendly_error(demo, demo_login):
    client = demo_login("owner@demo.example")
    response = client.post(
        "/import/",
        data={"data_type": "drivers", "file": (io.BytesIO(b"MZ"), "virus.exe")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Upload an Excel (.xlsx) or CSV file." in response.get_data(as_text=True)


# --- permissions and tenant isolation ------------------------------------------


def test_viewer_cannot_import(demo, demo_login):
    client = demo_login("viewer@demo.example")
    assert client.get("/import/").status_code == 403
    assert client.post("/import/", data={"data_type": "drivers"}).status_code == 403


@pytest.mark.isolation
def test_staged_upload_is_bound_to_its_tenant(demo, demo_login):
    client = demo_login("owner@demo.example")  # Red Draw
    token = _upload(client, "drivers_messy.xlsx", "drivers")
    other = demo_login("large-owner@demo.example")  # Blue Stem
    assert other.get(f"/import/{token}/map").status_code == 404
    assert other.post(f"/import/{token}/review", data={"action": "import"}).status_code == 404
    assert other.post(f"/import/{token}/cancel").status_code == 404


@pytest.mark.isolation
def test_cannot_undo_or_use_another_tenants_run_or_template(demo, demo_login):
    red = demo["tenants"][RED_DRAW]
    with tenant_scope(red):
        run = ImportRun(data_type="drivers", file_name="x.csv")
        template = ImportTemplate(name="Red's", data_type="drivers", column_mapping={})
        db.session.add_all([run, template])
        db.session.commit()
        run_id, template_id = run.id, template.id
    other = demo_login("large-owner@demo.example")
    assert other.post(f"/import/runs/{run_id}/undo").status_code == 404
    assert other.post(f"/import/templates/{template_id}/delete").status_code == 404
    response = other.post(
        "/import/",
        data={
            "data_type": "drivers",
            "template_id": str(template_id),
            "file": (io.BytesIO((SAMPLES / "drivers_messy.xlsx").read_bytes()), "d.xlsx"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


@pytest.mark.isolation
def test_invalid_token_format_is_404(demo, demo_login):
    client = demo_login("owner@demo.example")
    assert client.get("/import/..%2F..%2Fetc%2Fpasswd/map").status_code == 404
    assert client.get("/import/short/map").status_code == 404


def _engine_import(data_type, filename=None, csv_text=None, skip_errors=True):
    data = (SAMPLES / filename).read_bytes() if filename else csv_text.encode()
    headers, rows = read_table(filename or "x.csv", data)
    spec = SPECS[data_type]
    mapping = suggest_mapping(spec, headers)
    results = engine.build_rows(spec, headers, rows, mapping)
    if skip_errors:
        skipped = {r.index for r in results if r.errors}
        results = engine.build_rows(spec, headers, rows, mapping, skipped=skipped)
    return results


def test_training_import_matches_drivers_by_cdl(demo):
    with tenant_scope(demo["tenants"][RED_DRAW]):
        drivers = _engine_import("drivers", "drivers_messy.xlsx")
        engine.commit(SPECS["drivers"], drivers, file_name="d.xlsx", user_id=None)
        results = _engine_import("training", "training_messy.csv", skip_errors=False)
        errors = {r.line: r.errors for r in results if r.errors}
        assert "No driver with that CDL number" in errors[5]["cdl_number"]
        assert errors[6]["course_name"] == "Course is required"
        assert [r.values["category"] for r in results[:3]] == ["hazmat", "safety", "safety"]
        results = _engine_import("training", "training_messy.csv")
        run = engine.commit(SPECS["training"], results, file_name="t.csv", user_id=None)
        assert (run.rows_added, run.rows_skipped) == (3, 2)
        # Importing the same file again updates nothing and adds nothing.
        again = engine.commit(
            SPECS["training"],
            _engine_import("training", "training_messy.csv"),
            file_name="t.csv",
            user_id=None,
        )
        assert (again.rows_added, again.rows_updated) == (0, 0)


def test_drug_test_import(demo):
    red = demo["tenants"][RED_DRAW]
    with tenant_scope(red):
        cdl = db.session.scalars(select(Driver.cdl_number).order_by(Driver.id)).first()
        csv_text = (
            "CDL,Reason,Collection Date,Outcome\n"
            f"{cdl},Random,11/01/2026,NEG\n"
            f"{cdl},Post-Accident,2026-11-03,refusal\n"
            f"{cdl},Random,11/01/2026,neg\n"
            f"{cdl},Annual,2026-11-04,negative\n"
        )
        results = _engine_import("drug_tests", csv_text=csv_text, skip_errors=False)
        assert results[0].values["result"] == "negative"
        assert results[1].values == {
            **results[1].values,
            "test_type": "post_accident",
            "result": "refused",
        }
        assert "Duplicate of line 2" in results[2].errors["cdl_number"]
        assert "isn't a valid test type" in results[3].errors["test_type"]


def test_maintenance_import_and_unknown_unit(demo):
    red = demo["tenants"][RED_DRAW]
    with tenant_scope(red):
        unit = db.session.scalars(select(Vehicle.unit_number).order_by(Vehicle.id)).first()
        csv_text = (
            "Unit,Service Date,Description,Shop,Vendor,Next PM,Next Miles\n"
            f'{unit},2026-11-02,Oil change,Dealer,Panhandle Diesel,2027-02-01,"215,000"\n'
            "NOPE1,2026-11-02,Tires,In House,,,\n"
        )
        results = _engine_import("maintenance", csv_text=csv_text, skip_errors=False)
        assert results[0].values["shop_type"] == "outside"
        assert results[0].values["next_due_miles"] == 215000
        assert "No unit with that number" in results[1].errors["unit_number"]
        run = engine.commit(
            SPECS["maintenance"],
            _engine_import("maintenance", csv_text=csv_text),
            file_name="m.csv",
            user_id=None,
        )
        assert run.rows_added == 1

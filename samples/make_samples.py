"""Generate the deliberately messy sample spreadsheets in this folder.

    python samples/make_samples.py

Dates are relative to today, so re-run before a demo to keep "expiring soon"
rows expiring soon. Every name and number is fictional.

Each file has the problems real fleet spreadsheets have: odd headers, mixed
date formats, a duplicate, a blank required field and a bad value.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent


def make_drivers(today: date) -> Path:
    def d(days: int) -> date:
        return today + timedelta(days=days)

    us = "%m/%d/%Y"
    rows = [
        # Driver Name, CDL #, Lic State, Class, CDL Exp., DOT Physical Exp, Date Hired, Cell, Notes
        [
            "Hank Dobbs",
            "99 120 455",
            "TX",
            "A",
            d(700).isoformat(),
            d(16).strftime(us),
            "2025-02-03",
            "806-555-0141",
            "Physical due soon",
        ],
        [
            "Ruiz, Ana",
            "9945-1180",
            "tx",
            "A",
            d(500).strftime("%-m/%-d/%y"),
            d(300).strftime("%d-%b-%Y"),
            "06/01/2024",
            "806-555-0177",
            "Last, First format",
        ],
        [
            "Marcus Lee",
            "99301122",
            "TX",
            "B",
            datetime.combine(d(900), datetime.min.time()),
            d(120).strftime("%B %d, %Y"),
            "2023-11-15",
            "",
            "Real Excel date cell",
        ],
        [
            "Marcus Lee",
            "99-301122",
            "TX",
            "B",
            d(900).isoformat(),
            d(120).isoformat(),
            "2023-11-15",
            "",
            "Duplicate of the row above",
        ],
        [
            "Tom Pruitt",
            "",
            "TX",
            "A",
            d(400).isoformat(),
            d(200).isoformat(),
            "2025-08-20",
            "806-555-0102",
            "CDL number missing",
        ],
        [
            "Jo Fenner",
            "99442210",
            "TX",
            "A",
            d(650).isoformat(),
            "soon",
            "2022-04-11",
            "806-555-0193",
            "Bad date",
        ],
        [
            "Della Price",
            "99887701",
            "NM",
            "A",
            d(250).isoformat(),
            d(-6).strftime(us),
            "2021-09-30",
            "575-555-0110",
            "Physical already expired",
        ],
        [
            "Sam Whitt",
            "99652318",
            "TX",
            "A",
            d(1100).isoformat(),
            d(500).strftime(us),
            "2026-01-05",
            "806-555-0168",
            "",
        ],
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    ws.append(
        [
            "Driver Name",
            "CDL #",
            "Lic State",
            "Class",
            "CDL Exp.",
            "DOT Physical Exp",
            "Date Hired",
            "Cell",
            "Notes",
        ]
    )
    for row in rows:
        ws.append(row)
    ws["E4"].number_format = "mm/dd/yyyy"
    path = HERE / "drivers_messy.xlsx"
    wb.save(path)
    return path


def make_vehicles(today: date) -> Path:
    def d(days: int) -> date:
        return today + timedelta(days=days)

    rows = [
        ["Unit #", "Type", "Yr", "Make", "VIN Number", "Tag", "Reg Exp", "Annual Insp"],
        [
            "T201",
            "Truck",
            "2021",
            "Peterbilt",
            "9DEMO7RX4MN100201",
            "ABC-1201",
            d(200).strftime("%m/%d/%Y"),
            d(-90).isoformat(),
        ],
        [
            "T202",
            "tractor",
            "2019",
            "Kenworth",
            "9DEMO7RX4MN100202",
            "ABC-1202",
            d(20).isoformat(),
            d(-340).strftime("%m/%d/%y"),
        ],
        [
            "TR610",
            "TRL",
            "2016",
            "Wilson livestock",
            "9DEMO7TR4MN100610",
            "TRL-610",
            d(300).isoformat(),
            d(-30).isoformat(),
        ],
        [
            "TR611",
            "trailer",
            "2018",
            "Timpte hopper",
            "9DEMO7TR4MN100611",
            "TRL-611",
            "",
            d(-200).isoformat(),
        ],
        [
            "TR611",
            "Trailer",
            "2018",
            "Timpte hopper",
            "9DEMO7TR4MN100611",
            "TRL-611",
            d(100).isoformat(),
            d(-200).isoformat(),
        ],
        ["P01", "Pickup", "2022", "Ford", "9DEMO7PK4MN100001", "PU-001", d(150).isoformat(), ""],
    ]
    path = HERE / "vehicles_messy.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


def make_training(today: date) -> Path:
    def d(days: int) -> date:
        return today + timedelta(days=days)

    rows = [
        ["CDL", "Class Name", "Type", "Completed", "Valid Until"],
        [
            "99 120 455",
            "Hazmat Endorsement Training",
            "Hazmat",
            d(-700).isoformat(),
            d(25).isoformat(),
        ],
        [
            "9945-1180",
            "Defensive Driving",
            "safety",
            d(-30).strftime("%m/%d/%Y"),
            d(700).strftime("%m/%d/%Y"),
        ],
        ["99652318", "Winter Driving Safety", "Safety", d(-10).isoformat(), d(355).isoformat()],
        ["99000000", "Cargo Securement", "safety", d(-5).isoformat(), d(720).isoformat()],
        ["99887701", "", "safety", d(-60).isoformat(), d(300).isoformat()],
    ]
    path = HERE / "training_messy.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


if __name__ == "__main__":
    today = date.today()
    for maker in (make_drivers, make_vehicles, make_training):
        print("wrote", maker(today).relative_to(HERE.parent))

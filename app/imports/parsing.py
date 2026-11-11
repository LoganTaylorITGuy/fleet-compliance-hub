"""Read uploaded spreadsheets and parse the messy values found in them."""

from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta

import pandas as pd

MAX_ROWS = 2000
ALLOWED_EXTENSIONS = {".xlsx", ".csv"}


class ImportFileError(ValueError):
    """The upload couldn't be read as a spreadsheet."""


def read_table(filename: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    """Return (headers, rows) with every cell as a trimmed string.

    Everything is read as text so nothing is guessed before the user maps
    columns: "007" stays "007", and dates are parsed by our own rules.
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ImportFileError("Upload an Excel (.xlsx) or CSV file.")
    try:
        if ext == ".csv":
            frame = pd.read_csv(
                io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig"
            )
        else:
            frame = pd.read_excel(
                io.BytesIO(data), dtype=str, keep_default_na=False, engine="openpyxl"
            )
    except Exception as exc:  # pandas raises many types for bad files
        raise ImportFileError("That file couldn't be read. Is it a valid spreadsheet?") from exc

    headers = [str(h).strip() for h in frame.columns]
    if not headers or all(h.startswith("Unnamed") for h in headers):
        raise ImportFileError("The first row should contain column headers.")
    rows = [[_clean(v) for v in row] for row in frame.itertuples(index=False, name=None)]
    rows = [r for r in rows if any(r)]  # drop fully blank lines
    if not rows:
        raise ImportFileError("The file has headers but no data rows.")
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"Imports are limited to {MAX_ROWS} rows per file.")
    return headers, rows


def _clean(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


# --- values ------------------------------------------------------------------

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%m-%d-%y",
    "%m.%d.%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%b %d %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y/%m/%d",
)

EXCEL_EPOCH = date(1899, 12, 30)


def parse_date(text: str) -> date:
    """Parse the date formats small fleets actually use (US month-first).

    Raises ValueError with a plain-language message.
    """
    value = text.strip().replace("  ", " ")
    if re.fullmatch(r"\d{5}(\.0+)?", value):  # Excel serial day number
        serial = int(float(value))
        if 20000 < serial < 80000:
            return EXCEL_EPOCH + timedelta(days=serial)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'"{text}" isn\'t a date we recognize (try 2026-03-14 or 03/14/2026)')


def parse_int(text: str) -> int:
    cleaned = text.replace(",", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        raise ValueError(f'"{text}" isn\'t a whole number') from None


TRUE_WORDS = {"y", "yes", "true", "1", "x", "student"}
FALSE_WORDS = {"n", "no", "false", "0", ""}


def parse_bool(text: str) -> bool:
    word = text.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f'"{text}" should be yes or no')


def normalize_header(text: str) -> str:
    """'CDL Exp. Date' -> 'cdl exp date'."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

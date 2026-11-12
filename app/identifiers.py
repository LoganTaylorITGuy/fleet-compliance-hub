"""Normalize real-world identifiers so records from different sources match.

Spreadsheets and the ELD write the same CDL number, unit number or VIN in
different ways ("TR-501", "tr 501"). Both the spreadsheet import and the Motive
sync match on these keys, so the rule lives here rather than in either feature.
"""

from __future__ import annotations

import re


def normalize_key(text: str | None) -> str:
    """Uppercase and drop spaces and hyphens: " tr-501 " -> "TR501"."""
    return re.sub(r"[\s\-]", "", (text or "")).upper()

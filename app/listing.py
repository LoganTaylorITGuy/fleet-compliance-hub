"""Search and status filtering shared by the list pages."""

from __future__ import annotations

from flask import request

from .compliance import Level

LEVEL_CHOICES = [
    ("", "All statuses"),
    ("red", "Action needed"),
    ("yellow", "Due soon"),
    ("green", "Current"),
]


def level_filter() -> Level | None:
    value = request.args.get("status", "")
    return {"red": Level.RED, "yellow": Level.YELLOW, "green": Level.GREEN}.get(value)


def search_term() -> str:
    return request.args.get("q", "").strip()[:100]


def matches(term: str, *fields: str | None) -> bool:
    if not term:
        return True
    term = term.lower()
    return any(term in (f or "").lower() for f in fields)

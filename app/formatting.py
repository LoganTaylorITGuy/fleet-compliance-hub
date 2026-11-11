"""Jinja filters for dates and times. Times display in US Central, 24-hour."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from flask import Flask

LOCAL_TZ = ZoneInfo("America/Chicago")


def localtime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:  # SQLite drops tzinfo; values are stored in UTC
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def shortdate(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def label(value: str | None) -> str:
    """'previous_employer_check' -> 'Previous employer check'."""
    return (value or "").replace("_", " ").capitalize()


def register_filters(app: Flask) -> None:
    app.add_template_filter(localtime)
    app.add_template_filter(shortdate)
    app.add_template_filter(label)

"""The app's idea of "now" and "today": US Central time.

A server running on UTC would otherwise flip to tomorrow at 18:00 CST and mark
things expired early. Tests pass explicit dates to the rules instead.
"""

from __future__ import annotations

from datetime import date, datetime

from .formatting import LOCAL_TZ


def now() -> datetime:
    return datetime.now(LOCAL_TZ)


def today() -> date:
    return now().date()

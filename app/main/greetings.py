"""Context-aware greetings for the Home page.

Pure functions: a first name, a local datetime and a seed in, a Greeting out.
The headline follows the time of day; the tagline adds a little personality,
with special lines for Monday mornings, Friday afternoons and weekends.

The tagline is chosen from a stable hash of (seed, date, part of day), so it
stays the same on refresh and changes with the day and the time of day.
Different users (different seeds) see different lines.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Greeting:
    headline: str
    tagline: str


HEADLINES = {
    "late_night": "Burning the midnight oil",
    "morning": "Good morning",
    "afternoon": "Good afternoon",
    "evening": "Good evening",
    "night": "Working late",
}

TAGLINES = {
    "late_night": (
        "Night shift crew, welcome in.",
        "The road never sleeps, and apparently neither do you.",
        "Quiet hours are perfect for catching up on files.",
    ),
    "morning": (
        "Coffee's hot and the fleet's rolling. Here's what needs you.",
        "Fresh day, fresh logs. Here's where things stand.",
        "Pre-trip for your paperwork starts right here.",
        "Early bird gets the clean inspection.",
    ),
    "afternoon": (
        "Halfway through the day. Let's keep everything green.",
        "Good time to knock out what's due this month.",
        "Miles are getting logged. Here's your rundown.",
    ),
    "evening": (
        "Wrapping up? Here's anything that can't wait until tomorrow.",
        "Trucks are heading home. Let's make sure the files are too.",
        "One last look before you clock out.",
    ),
    "night": (
        "The day's miles are in. Here's what's left.",
        "Late one tonight. Here's the short list.",
    ),
}

SPECIAL_TAGLINES = {
    "monday_morning": ("New week, clean slate. Let's get ahead of what's due.",),
    "friday_afternoon": ("Almost the weekend. Let's leave nothing expiring behind.",),
    "weekend": (
        "Weekend shift? Thanks for keeping the wheels turning.",
        "Even on the weekend, the fleet keeps moving.",
    ),
}

MONDAY, FRIDAY, SATURDAY = 0, 4, 5


def part_of_day(hour: int) -> str:
    """00-04 late night, 05-11 morning, 12-16 afternoon, 17-21 evening, 22-23 night."""
    if hour < 5:
        return "late_night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 22:
        return "evening"
    return "night"


def _tagline_pool(moment: datetime, part: str) -> tuple[str, ...]:
    weekday = moment.weekday()
    if weekday >= SATURDAY and part != "late_night":
        return SPECIAL_TAGLINES["weekend"]
    if weekday == MONDAY and part == "morning":
        return SPECIAL_TAGLINES["monday_morning"]
    if weekday == FRIDAY and part == "afternoon":
        return SPECIAL_TAGLINES["friday_afternoon"]
    return TAGLINES[part]


def greet(name: str, moment: datetime, seed: int = 0) -> Greeting:
    """The greeting for ``name`` (a first name) at local time ``moment``."""
    part = part_of_day(moment.hour)
    headline = HEADLINES[part]
    if name:
        headline = f"{headline}, {name}"
    pool = _tagline_pool(moment, part)
    key = f"{seed}:{moment.date().isoformat()}:{part}".encode()
    return Greeting(headline, pool[zlib.crc32(key) % len(pool)])


def first_name(full_name: str | None) -> str:
    """ "Dana Whitfield" -> "Dana"; blank -> ""."""
    return (full_name or "").strip().split(" ")[0]

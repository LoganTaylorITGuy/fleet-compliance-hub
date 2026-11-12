"""Home page greetings: time of day, special days, stable choice, names."""

from datetime import datetime

import pytest

from app.formatting import LOCAL_TZ
from app.main.greetings import (
    HEADLINES,
    SPECIAL_TAGLINES,
    TAGLINES,
    first_name,
    greet,
    part_of_day,
)

TUESDAY = datetime(2026, 11, 17, tzinfo=LOCAL_TZ)  # an ordinary weekday


def at(day: datetime, hour: int) -> datetime:
    return day.replace(hour=hour, minute=30)


@pytest.mark.parametrize(
    ("hour", "part"),
    [
        (0, "late_night"),
        (4, "late_night"),
        (5, "morning"),
        (11, "morning"),
        (12, "afternoon"),
        (16, "afternoon"),
        (17, "evening"),
        (21, "evening"),
        (22, "night"),
        (23, "night"),
    ],
)
def test_part_of_day_boundaries(hour, part):
    assert part_of_day(hour) == part


@pytest.mark.parametrize("hour", [2, 9, 14, 19, 23])
def test_weekday_greeting_matches_time_of_day(hour):
    part = part_of_day(hour)
    greeting = greet("Dana", at(TUESDAY, hour), seed=1)
    assert greeting.headline == f"{HEADLINES[part]}, Dana"
    assert greeting.tagline in TAGLINES[part]


def test_monday_morning_and_friday_afternoon_have_their_own_lines():
    monday, friday = TUESDAY.replace(day=16), TUESDAY.replace(day=20)
    assert greet("Dana", at(monday, 8)).tagline in SPECIAL_TAGLINES["monday_morning"]
    assert greet("Dana", at(friday, 15)).tagline in SPECIAL_TAGLINES["friday_afternoon"]
    assert greet("Dana", at(friday, 9)).tagline in TAGLINES["morning"]


def test_weekend_lines_except_late_at_night():
    saturday = TUESDAY.replace(day=21)
    assert greet("Dana", at(saturday, 10)).tagline in SPECIAL_TAGLINES["weekend"]
    assert greet("Dana", at(saturday, 2)).tagline in TAGLINES["late_night"]


def test_choice_is_stable_for_a_user_and_moment():
    moment = at(TUESDAY, 9)
    assert greet("Dana", moment, seed=7) == greet("Dana", moment.replace(minute=59), seed=7)


def test_different_users_and_days_get_variety():
    taglines = {greet("A", at(TUESDAY.replace(day=d), 9), seed=s).tagline
                for d in range(10, 15) for s in range(5)}  # fmt: skip
    assert len(taglines) > 1


def test_no_name_still_greets():
    assert greet("", at(TUESDAY, 9)).headline == "Good morning"


@pytest.mark.parametrize(
    ("full", "first"), [("Dana Whitfield", "Dana"), ("  Jo  ", "Jo"), ("", ""), (None, "")]
)
def test_first_name(full, first):
    assert first_name(full) == first

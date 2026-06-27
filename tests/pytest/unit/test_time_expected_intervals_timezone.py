"""Regression: get_expected_intervals_for_date must handle missing timezones.

When an area's timezone service has not resolved a zone, the caller passes
``None`` (or the string ``"None"``). The old code reached ``ZoneInfo("None")``,
which triggered a blocking tzdata load inside the event loop (Home Assistant
flags this as a blocking call) before failing/raising. The fix returns a normal
(96-interval) day at a guard, BEFORE constructing any ZoneInfo or DSTHandler.

These tests patch DSTHandler to assert that early-return path is taken for
missing timezones, and leave it real for valid zones to confirm DST detection
still works.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

from custom_components.ge_spot.const.time import TimeInterval

NORMAL = TimeInterval.get_intervals_per_day()  # 96


def _intervals_guarded(tz_value):
    """For a missing timezone the helper must return before touching DSTHandler.

    DSTHandler is imported inside the function from its source module, so we
    patch it there. If the guard is removed, the function either constructs a
    DSTHandler (None case) or raises in ZoneInfo (the "None"/"" cases) — both
    fail this helper.
    """
    with patch(
        "custom_components.ge_spot.timezone.dst_handler.DSTHandler"
    ) as dst_handler:
        result = TimeInterval.get_expected_intervals_for_date(
            datetime(2026, 6, 27), tz_value
        )
        dst_handler.assert_not_called()
    return result


def test_none_timezone_returns_at_guard():
    assert _intervals_guarded(None) == NORMAL


def test_string_none_returns_at_guard():
    assert _intervals_guarded("None") == NORMAL


def test_empty_string_returns_at_guard():
    assert _intervals_guarded("") == NORMAL


def test_valid_zoneinfo_object_still_works():
    result = TimeInterval.get_expected_intervals_for_date(
        datetime(2026, 6, 27), ZoneInfo("Europe/Stockholm")
    )
    assert result == NORMAL


def test_valid_string_still_works():
    result = TimeInterval.get_expected_intervals_for_date(
        datetime(2026, 6, 27), "Europe/Stockholm"
    )
    assert result == NORMAL


def test_dst_transition_day_still_detected_with_valid_zone():
    # 2026-03-29 is the European spring-forward day (92 intervals).
    result = TimeInterval.get_expected_intervals_for_date(
        datetime(2026, 3, 29), "Europe/Stockholm"
    )
    assert result == TimeInterval.get_intervals_per_day_dst_spring()  # 92

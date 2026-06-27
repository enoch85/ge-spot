"""Regression: naive ISO timestamps must be localized to the source timezone.

TimestampParser.parse() has a general-ISO branch. The offset-detection used
`"+" in s or "-" in s and "T" in s`; because `and` binds tighter than `or` and
the branch already runs under `if "T" in s`, this reduced to `"+" in s or
"-" in s`. A naive ISO like "2025-03-30T10:00:00" contains "-" (date separators),
so it wrongly took the "has offset" path and was returned NAIVE instead of being
localized to the source timezone. Only a real trailing offset (+HH:MM / -HHMM)
should take that path.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from custom_components.ge_spot.timezone.parser import TimestampParser


def test_naive_iso_gets_source_timezone_attached():
    result = TimestampParser().parse("2025-03-30T10:00:00", "Europe/Stockholm")
    # Must be timezone-aware (the bug returned a naive datetime).
    assert result.tzinfo is not None, "naive ISO must be localized, got naive"
    # Wall-clock time is unchanged; the source timezone is attached.
    assert (result.hour, result.minute) == (10, 0)
    assert result.utcoffset() == ZoneInfo("Europe/Stockholm").utcoffset(
        datetime(2025, 3, 30, 10, 0)
    )


def test_iso_with_offset_is_preserved_and_converted():
    # 10:00+05:00 == 05:00 UTC; converted into Europe/Stockholm it is the same
    # instant (07:00 CEST on 2025-03-30).
    result = TimestampParser().parse("2025-03-30T10:00:00+05:00", "Europe/Stockholm")
    assert result.tzinfo is not None
    assert result.astimezone(timezone.utc) == datetime(
        2025, 3, 30, 5, 0, tzinfo=timezone.utc
    )


def test_iso_with_z_suffix_still_handled():
    # Z (UTC) timestamps are handled by the dedicated branch and converted.
    result = TimestampParser().parse("2025-03-30T10:00:00Z", "Europe/Stockholm")
    assert result.tzinfo is not None
    assert result.astimezone(timezone.utc) == datetime(
        2025, 3, 30, 10, 0, tzinfo=timezone.utc
    )

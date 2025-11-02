"""DST transition handling utilities."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

from ..const.time import DSTTransitionType
from ..const.network import Network

_LOGGER = logging.getLogger(__name__)


class DSTHandler:
    """Handler for DST transitions."""

    def __init__(self, timezone=None):
        """Initialize with optional timezone."""
        self.timezone = timezone or dt_util.DEFAULT_TIME_ZONE

    def is_dst_transition_day(self, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Check if date is a DST transition day.

        Args:
            dt: The datetime to check (defaults to now)

        Returns:
            Tuple of (is_transition, transition_type)
            where transition_type is 'spring_forward' or 'fall_back'
        """
        # Use provided time or current time in the configured timezone
        if dt is None:
            dt = dt_util.now(self.timezone)

        # Make sure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.timezone)

        # Get timezone - use dt's timezone if available, otherwise use self.timezone
        tz = dt.tzinfo if dt.tzinfo else self.timezone

        # Extract date components
        year, month, day_num = dt.year, dt.month, dt.day

        # Create aware datetime at midnight for current day and next day
        # Using ZoneInfo-style: create with tzinfo directly
        day = datetime(year, month, day_num, 0, 0, 0, tzinfo=tz)
        day_plus_1 = datetime(year, month, day_num, 0, 0, 0, tzinfo=tz) + timedelta(
            days=1
        )

        # Convert to UTC to calculate actual elapsed time (not wall clock time)
        # This is necessary because datetime arithmetic ignores DST transitions
        day_utc = day.astimezone(timezone.utc)
        day_plus_1_utc = day_plus_1.astimezone(timezone.utc)

        # Calculate the difference in hours using UTC times
        # This will be 23, 24, or 25 hours depending on DST transition
        diff_hours = (
            day_plus_1_utc - day_utc
        ).total_seconds() / Network.Defaults.SECONDS_PER_HOUR

        # Check if it's a DST transition day
        if abs(diff_hours - 24) < 0.1:
            # Normal day (24 hours)
            return False, ""
        elif diff_hours < 24:
            # Spring forward day (23 hours)
            _LOGGER.debug(
                f"Detected DST spring forward day: {dt.date()} with {diff_hours} hours"
            )
            return True, DSTTransitionType.SPRING_FORWARD
        else:
            # Fall back day (25 hours)
            _LOGGER.debug(
                f"Detected DST fall back day: {dt.date()} with {diff_hours} hours"
            )
            return True, DSTTransitionType.FALL_BACK

    def get_dst_offset_info(self, dt: Optional[datetime] = None) -> str:
        """Get DST offset info as a string (e.g. '+1 hour').

        Args:
            dt: The datetime to check (defaults to now)

        Returns:
            Formatted DST offset string
        """
        if dt is None:
            dt = dt_util.now(self.timezone)

        if dt.tzinfo is None:
            return "unknown timezone"

        # Get DST offset in seconds
        dst_seconds = dt.dst().total_seconds()

        # Convert to hours and format
        if dst_seconds == 0:
            return "no DST offset"

        dst_hours = dst_seconds / Network.Defaults.SECONDS_PER_HOUR
        hour_text = "hour" if abs(dst_hours) == 1 else "hours"
        return f"{dst_hours:+.0f} {hour_text}"


def get_day_hours(date, timezone):
    """Get all hours for a day with DST awareness.

    Args:
        date: Date object or datetime object
        timezone: ZoneInfo timezone object or string

    Returns:
        List of dict with {"hour": int, "suffix": str} for each hour in the day.
        Normal day: 24 hours (0-23)
        DST fall-back: 25 hours (0-1, 2 (first), 2 (second), 3-23)
        DST spring-forward: 23 hours (0-1, 3-23, hour 2 is skipped)

    Example:
        Normal day: [{"hour": 0}, {"hour": 1}, ..., {"hour": 23}]
        Fall-back: [{"hour": 0}, {"hour": 1}, {"hour": 2, "suffix": "_1"},
                    {"hour": 2, "suffix": "_2"}, {"hour": 3}, ..., {"hour": 23}]
        Spring-forward: [{"hour": 0}, {"hour": 1}, {"hour": 3}, ..., {"hour": 23}]
    """
    # Convert date to datetime if needed
    if hasattr(date, "date"):
        # It's already a datetime
        dt = date
    else:
        # It's a date, convert to datetime at midnight
        dt = datetime.combine(date, datetime.min.time())

    # Ensure timezone is ZoneInfo object
    if isinstance(timezone, str):
        timezone = ZoneInfo(timezone)

    # Make datetime timezone-aware if it isn't
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone)

    # Check for DST transition
    dst_handler = DSTHandler(timezone)
    is_dst, dst_type = dst_handler.is_dst_transition_day(dt)

    result = []

    if is_dst and dst_type == DSTTransitionType.FALL_BACK:
        # Fall-back: 25 hours (hour 2 appears twice)
        # Hours 0-1
        for hour in range(0, 2):
            result.append({"hour": hour})
        # Hour 2 first occurrence (DST)
        for suffix in ["_1", "_2"]:
            result.append({"hour": 2, "suffix": suffix})
        # Hours 3-23
        for hour in range(3, 24):
            result.append({"hour": hour})

    elif is_dst and dst_type == DSTTransitionType.SPRING_FORWARD:
        # Spring-forward: 23 hours (hour 2 is skipped)
        # Hours 0-1
        for hour in range(0, 2):
            result.append({"hour": hour})
        # Hour 2 is skipped
        # Hours 3-23
        for hour in range(3, 24):
            result.append({"hour": hour})
    else:
        # Normal day: 24 hours
        for hour in range(0, 24):
            result.append({"hour": hour})

    return result

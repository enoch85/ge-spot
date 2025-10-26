"""DST transition handling utilities."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional

from homeassistant.util import dt as dt_util

from ..const.time import DSTTransitionType

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
        diff_hours = (day_plus_1_utc - day_utc).total_seconds() / 3600

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

        dst_hours = dst_seconds / 3600
        hour_text = "hour" if abs(dst_hours) == 1 else "hours"
        return f"{dst_hours:+.0f} {hour_text}"

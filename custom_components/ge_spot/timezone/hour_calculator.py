"""Hour calculation utilities."""
import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .dst_handler import DSTHandler
from ..const.time import DSTTransitionType, TimezoneConstants, TimezoneReference

_LOGGER = logging.getLogger(__name__)

class HourCalculator:
    """Calculator for hour-related operations."""

    def __init__(self, timezone=None, system_timezone=None, area_timezone=None, timezone_reference=None):
        """Initialize with optional timezone."""
        self.timezone = timezone or dt_util.DEFAULT_TIME_ZONE
        # Always use system timezone for display purposes
        self.system_timezone = system_timezone or self.timezone
        # Use area-specific timezone if provided
        self.area_timezone = area_timezone
        # Store timezone reference mode
        self.timezone_reference = timezone_reference
        self.dst_handler = DSTHandler(self.timezone)

    def get_current_hour_key(self) -> str:
        """Get the current hour formatted as HH:00."""
        # Get current time in the specified timezone
        now = dt_util.now(self.timezone)
        now_display = now  # Initialize now_display with a default value

        # If using Home Assistant Time mode, we need to compensate for timezone differences
        if self.timezone_reference == TimezoneReference.HOME_ASSISTANT:
            if self.area_timezone and self.area_timezone != self.system_timezone:
                # Get the current time in both timezones to calculate the correct offset
                now_system = datetime.now(self.system_timezone)
                now_area = datetime.now(self.area_timezone)

                # Log the actual times for debugging
                _LOGGER.debug(f"System time: {now_system.isoformat()}, Area time: {now_area.isoformat()}")

                # Calculate total seconds difference to handle DST and other edge cases
                time_diff_seconds = (now_area.replace(tzinfo=None) - now_system.replace(tzinfo=None)).total_seconds()
                hour_diff = round(time_diff_seconds / 3600)  # Convert to hours and round to nearest hour

                _LOGGER.debug(f"Time difference: {time_diff_seconds} seconds, {hour_diff} hours")

                # Apply the offset in reverse to compensate
                adjusted_hour = (now.hour - hour_diff) % 24
                hour_key = f"{adjusted_hour:02d}:00"
                _LOGGER.debug(f"Applied timezone compensation of {-hour_diff} hours: {now.hour}:00 → {adjusted_hour}:00")
                return hour_key

        # If area timezone is provided and using Local Area Time mode, use it for determining the current hour
        elif self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            # Use astimezone to properly convert the time to the area timezone
            now_display = now.astimezone(self.area_timezone)
            _LOGGER.debug(f"Using area timezone {self.area_timezone} for hour calculation")
        else:
            # Otherwise use system timezone for display
            now_display = now.astimezone(self.system_timezone)

        # Check for DST transition
        is_transition, transition_type = self.dst_handler.is_dst_transition_day(now)

        # Special handling for fall back transition during the ambiguous hour
        if is_transition and transition_type == DSTTransitionType.FALL_BACK and now.hour == 2:
            # Check if we're in the first or second occurrence of 2:00
            dst_offset = now.dst().total_seconds()

            if dst_offset > 0:
                # First time through 2:00 (still on DST)
                _LOGGER.debug("Current hour during fall back DST transition: first 02:00")
                return "02:00"
            else:
                # Second time through 2:00 (DST ended)
                _LOGGER.debug("Current hour during fall back DST transition: second 02:00 (03:00)")
                return "03:00"

        # Normal case - use the current hour in the appropriate timezone
        hour_key = f"{now_display.hour:02d}:00"
        display_tz = self.area_timezone if self.area_timezone else self.system_timezone
        _LOGGER.debug(f"Current hour determined as {hour_key} from datetime {now_display.isoformat()} (timezone: {display_tz})")
        return hour_key

    def get_next_hour_key(self) -> str:
        """Get the next hour formatted as HH:00."""
        # Get current time in the specified timezone
        now = dt_util.now(self.timezone)
        now_display = now  # Initialize now_display with a default value

        # If area timezone is provided, use it for determining the next hour
        if self.area_timezone:
            now_display = now.astimezone(self.area_timezone)
        else:
            # Otherwise use system timezone for display
            now_display = now.astimezone(self.system_timezone)

        # Calculate next hour
        next_hour = (now_display.hour + 1) % 24

        # Check for DST transition
        is_transition, transition_type = self.dst_handler.is_dst_transition_day(now)

        # Special handling for DST transitions
        if is_transition:
            if transition_type == DSTTransitionType.SPRING_FORWARD and now_display.hour == 1 and next_hour == 2:
                # Skip from 1:00 to 3:00
                _LOGGER.debug("Next hour during spring forward: skipping from 01:00 to 03:00")
                return "03:00"
            elif transition_type == DSTTransitionType.FALL_BACK and now_display.hour == 2:
                # Check if we're in the first occurrence of 2:00
                dst_offset = now.dst().total_seconds()
                if dst_offset > 0 and TimezoneConstants.DST_OPTIONS["fall_back_first"]:
                    # First time through 2:00, next is second 2:00
                    _LOGGER.debug("Next hour during fall back: second 02:00")
                    return "02:00"

        # Log next hour determination for debugging
        next_hour_key = f"{next_hour:02d}:00"
        _LOGGER.debug(f"Next hour determined as {next_hour_key} from current hour {now_display.hour}")

        # Normal case
        return next_hour_key

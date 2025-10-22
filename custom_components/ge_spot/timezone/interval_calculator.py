"""Interval calculation utilities."""

import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .dst_handler import DSTHandler
from ..const.time import (
    DSTTransitionType,
    TimezoneConstants,
    TimezoneReference,
    TimeInterval,
)

_LOGGER = logging.getLogger(__name__)


class IntervalCalculator:
    """Calculator for time interval operations."""

    def __init__(
        self,
        timezone=None,
        system_timezone=None,
        area_timezone=None,
        timezone_reference=None,
    ):
        """Initialize with optional timezone."""
        self.timezone = timezone or dt_util.DEFAULT_TIME_ZONE
        # Always use system timezone for display purposes
        self.system_timezone = system_timezone or self.timezone
        # Use area-specific timezone if provided
        self.area_timezone = area_timezone
        # Store timezone reference mode
        self.timezone_reference = timezone_reference
        self.dst_handler = DSTHandler(self.timezone)

    def _round_to_interval(self, dt: datetime) -> datetime:
        """Round datetime to nearest interval boundary.

        Uses configured interval duration from TimeInterval.DEFAULT.
        Works for any interval duration (15-min, hourly, etc.).
        """
        interval_minutes = TimeInterval.get_interval_minutes()
        minute = (dt.minute // interval_minutes) * interval_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)

    def get_current_interval_key(self) -> str:
        """Get the current interval formatted as HH:MM."""
        # Get current time in the specified timezone
        now = dt_util.now(self.timezone)
        now_display = now  # Initialize now_display with a default value

        _LOGGER.debug(
            f"IntervalCalculator input: timezone={self.timezone}, system_timezone={self.system_timezone}, area_timezone={self.area_timezone}, timezone_reference={self.timezone_reference}"
        )

        # If using Home Assistant Time mode, we need to compensate for timezone differences
        if self.timezone_reference == TimezoneReference.HOME_ASSISTANT:
            if self.area_timezone and self.area_timezone != self.system_timezone:
                # Get the current time in both timezones to calculate the correct offset
                now_system = datetime.now(self.system_timezone)
                now_area = datetime.now(self.area_timezone)

                # Log the actual times for debugging
                _LOGGER.debug(
                    f"System time: {now_system.isoformat()}, Area time: {now_area.isoformat()}"
                )

                # Calculate total seconds difference to handle DST and other edge cases
                time_diff_seconds = (
                    now_area.replace(tzinfo=None) - now_system.replace(tzinfo=None)
                ).total_seconds()
                hour_diff = round(
                    time_diff_seconds / 3600
                )  # Convert to hours and round to nearest hour

                _LOGGER.debug(
                    f"IntervalCalculator compensation: now_system={now_system}, now_area={now_area}, hour_diff={hour_diff}"
                )

                # Round to interval and apply the offset
                rounded = self._round_to_interval(now)
                adjusted_hour = (rounded.hour - hour_diff) % 24
                interval_key = f"{adjusted_hour:02d}:{rounded.minute:02d}"
                _LOGGER.debug(
                    f"Applied timezone compensation of {-hour_diff} hours: {rounded.hour}:{rounded.minute:02d} → {interval_key}"
                )
                return interval_key

        # If area timezone is provided and using Local Area Time mode, use it for determining the current interval
        elif (
            self.timezone_reference == TimezoneReference.LOCAL_AREA
            and self.area_timezone
        ):
            # Use astimezone to properly convert the time to the area timezone
            now_display = now.astimezone(self.area_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using area_timezone: now_display={now_display}, area_timezone={self.area_timezone}"
            )
        else:
            # Otherwise use system timezone for display
            now_display = now.astimezone(self.system_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using system_timezone: now_display={now_display}, system_timezone={self.system_timezone}"
            )

        # Round to interval boundary
        rounded = self._round_to_interval(now_display)

        # Check for DST transition
        is_transition, transition_type = self.dst_handler.is_dst_transition_day(now)

        _LOGGER.debug(
            f"IntervalCalculator DST: is_transition={is_transition}, transition_type={transition_type}, now={now}"
        )

        # Special handling for fall back transition during the ambiguous hour
        if (
            is_transition
            and transition_type == DSTTransitionType.FALL_BACK
            and now.hour == 2
        ):
            # Check if we're in the first or second occurrence of 2:00
            dst_offset = now.dst().total_seconds()

            if dst_offset > 0:
                # First time through 2:00 (still on DST)
                _LOGGER.debug(
                    "Current interval during fall back DST transition: first 02:XX"
                )
                return f"02:{rounded.minute:02d}"
            else:
                # Second time through 2:00 (DST ended)
                _LOGGER.debug(
                    "Current interval during fall back DST transition: second 02:XX (03:XX)"
                )
                return f"03:{rounded.minute:02d}"

        # Normal case - use the current interval in the appropriate timezone
        interval_key = f"{rounded.hour:02d}:{rounded.minute:02d}"
        display_tz = self.area_timezone if self.area_timezone else self.system_timezone
        _LOGGER.debug(
            f"IntervalCalculator result: interval_key={interval_key}, rounded={rounded}, display_tz={display_tz}"
        )
        return interval_key

    def get_next_interval_key(self) -> str:
        """Get the next interval formatted as HH:MM."""
        # Get current time in the specified timezone
        now = dt_util.now(self.timezone)
        now_display = now  # Initialize now_display with a default value

        _LOGGER.debug(
            f"IntervalCalculator input: timezone={self.timezone}, system_timezone={self.system_timezone}, area_timezone={self.area_timezone}, timezone_reference={self.timezone_reference}"
        )

        # If area timezone is provided, use it for determining the next interval
        if self.area_timezone:
            now_display = now.astimezone(self.area_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using area_timezone: now_display={now_display}, area_timezone={self.area_timezone}"
            )
        else:
            # Otherwise use system timezone for display
            now_display = now.astimezone(self.system_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using system_timezone: now_display={now_display}, system_timezone={self.system_timezone}"
            )

        # Round to current interval and calculate next
        rounded = self._round_to_interval(now_display)
        interval_minutes = TimeInterval.get_interval_minutes()
        next_interval = rounded + timedelta(minutes=interval_minutes)

        # Check for DST transition
        is_transition, transition_type = self.dst_handler.is_dst_transition_day(now)

        _LOGGER.debug(
            f"IntervalCalculator DST: is_transition={is_transition}, transition_type={transition_type}, now={now}"
        )

        # Special handling for DST transitions
        if is_transition:
            if (
                transition_type == DSTTransitionType.SPRING_FORWARD
                and now_display.hour == 1
            ):
                # Check if next interval would fall in the skipped hour (2:XX)
                if next_interval.hour == 2:
                    # Skip to 3:00
                    _LOGGER.debug(
                        "Next interval during spring forward: skipping from 01:XX to 03:00"
                    )
                    return "03:00"
            elif (
                transition_type == DSTTransitionType.FALL_BACK and now_display.hour == 2
            ):
                # Check if we're in the first occurrence of 2:XX
                dst_offset = now.dst().total_seconds()
                if dst_offset > 0:
                    # First time through 2:XX, next moves forward normally
                    _LOGGER.debug(
                        "Next interval during fall back first 02:XX: moving forward normally"
                    )
                    return f"{next_interval.hour:02d}:{next_interval.minute:02d}"
                else:
                    # Second time through 2:XX, next is normal 3:XX
                    _LOGGER.debug(
                        "Next interval during fall back second 02:XX: normal next interval"
                    )
                    return f"{next_interval.hour:02d}:{next_interval.minute:02d}"

        # Log next interval determination for debugging
        next_interval_key = f"{next_interval.hour:02d}:{next_interval.minute:02d}"
        _LOGGER.debug(
            f"IntervalCalculator result: next_interval_key={next_interval_key}, next_interval={next_interval}"
        )

        # Normal case
        return next_interval_key

    def get_interval_key_for_datetime(self, dt: datetime) -> str:
        """Get the interval key for a specific datetime.

        Args:
            dt: Datetime to get interval key for

        Returns:
            Interval key in format HH:MM
        """
        # Convert to target timezone
        target_dt = dt

        _LOGGER.debug(
            f"IntervalCalculator input: dt={dt}, timezone_reference={self.timezone_reference}, area_timezone={self.area_timezone}, system_timezone={self.system_timezone}"
        )

        # If using Local Area Time mode and area timezone is available
        if (
            self.timezone_reference == TimezoneReference.LOCAL_AREA
            and self.area_timezone
        ):
            target_dt = dt.astimezone(self.area_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using area_timezone: target_dt={target_dt}, area_timezone={self.area_timezone}"
            )
        # Otherwise use Home Assistant Time mode
        else:
            target_dt = dt.astimezone(self.system_timezone)
            _LOGGER.debug(
                f"IntervalCalculator using system_timezone: target_dt={target_dt}, system_timezone={self.system_timezone}"
            )

        # Round to interval boundary
        rounded = self._round_to_interval(target_dt)

        # Generate the interval key
        interval_key = f"{rounded.hour:02d}:{rounded.minute:02d}"
        _LOGGER.debug(
            f"IntervalCalculator result: interval_key={interval_key}, rounded={rounded}"
        )

        return interval_key

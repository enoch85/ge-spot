"""Timezone conversion utilities."""
import logging
from datetime import datetime, time, timedelta, date
from typing import Dict, Any, Optional

from homeassistant.util import dt as dt_util

from .timezone_utils import get_timezone_object, get_source_timezone, convert_datetime, localize_datetime
from ..const.time import DSTTransitionType, TimezoneConstants

_LOGGER = logging.getLogger(__name__)

class TimezoneConverter:
    """Handles timezone conversions."""

    def __init__(self, default_target_tz=None):
        """Initialize with optional default target timezone."""
        self.default_target_tz = default_target_tz or dt_util.DEFAULT_TIME_ZONE

    def convert(self, dt: datetime, target_tz=None, source_tz=None) -> datetime:
        """Convert datetime with explicit timezone handling.

        Args:
            dt: Datetime object (naive or aware)
            target_tz: Target timezone (defaults to instance default)
            source_tz: Source timezone (required if dt is naive)

        Returns:
            Datetime in target timezone

        Raises:
            ValueError: If dt is naive and no source_tz provided
        """
        # Use the target timezone or default
        target = target_tz or self.default_target_tz

        # Use the convert_datetime function from timezone_utils
        try:
            return convert_datetime(dt, target, source_tz)
        except Exception as e:
            _LOGGER.error(f"Error converting datetime: {e}")
            raise

    def convert_hourly_prices(self, hourly_prices: Dict[str, float],
                             source_timezone: str, target_tz=None,
                             today_date=None, area_timezone=None) -> Dict[str, float]:
        """Convert hourly prices from source timezone to target timezone.

        Args:
            hourly_prices: Dict mapping hour strings to prices
            source_timezone: Source timezone string or source identifier
            target_tz: Target timezone (defaults to instance default)
            today_date: Optional date to use (defaults to today)
            area_timezone: Area-specific timezone (takes precedence over target_tz)

        Returns:
            Dict with hours adjusted to target timezone or area_timezone

        Raises:
            ValueError: If source_timezone is invalid
        """
        if not hourly_prices:
            return {}

        try:
            # Get timezone objects
            source_tz = get_timezone_object(source_timezone)
            if not source_tz:
                # Try to get timezone from source type constant
                source_tz_str = get_source_timezone(source_timezone)
                source_tz = get_timezone_object(source_tz_str)

            if not source_tz:
                error_msg = f"Invalid source timezone: {source_timezone}, cannot proceed with conversion"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)

            # Determine target timezone - area_timezone takes precedence if provided
            if area_timezone:
                if isinstance(area_timezone, str):
                    area_tz_obj = get_timezone_object(area_timezone)
                    if not area_tz_obj:
                        _LOGGER.warning(f"Invalid area timezone: {area_timezone}, falling back to target timezone")
                        area_timezone = None
                    else:
                        target = area_tz_obj
                        _LOGGER.debug(f"Using area-specific timezone for price conversion: {area_timezone}")
                else:
                    # Assume it's already a timezone object
                    target = area_timezone
                    _LOGGER.debug(f"Using area-specific timezone object for price conversion")
            else:
                # Use specified target timezone or default
                target = target_tz or self.default_target_tz
                if isinstance(target, str):
                    target = get_timezone_object(target)
                    _LOGGER.debug(f"Using target timezone for price conversion: {target_tz}")

            if today_date is None:
                today_date = dt_util.now(target).date()
            elif isinstance(today_date, datetime):
                today_date = today_date.date()

            converted = {}

            # Track hours that have already been processed
            processed_hours = set()

            for hour_str, price in hourly_prices.items():
                try:
                    # Check if hour_str is in ISO format (contains 'T')
                    if "T" in hour_str:
                        try:
                            # Parse ISO format date
                            source_dt = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                            # Already has date information, no need to combine with today_date

                            # Use timezone_utils functions for conversion
                            source_dt = localize_datetime(source_dt, source_tz)
                            target_dt = convert_datetime(source_dt, target)

                            # CRITICAL: Preserve ISO format for dates to distinguish tomorrow's data
                            # Use format_hour_key utility function to ensure consistent formatting
                            from .timezone_utils import format_hour_key
                            target_hour_str = format_hour_key(target_dt)
                        except (ValueError, TypeError) as e:
                            _LOGGER.error(f"Failed to parse ISO date: {hour_str} - {e}")
                            converted[hour_str] = price  # Keep original in case of error
                            continue
                    else:
                        # Original code for "HH:00" format
                        hour = int(hour_str.split(":")[0])
                        source_dt = datetime.combine(today_date, time(hour=hour))

                    # Use timezone_utils functions for conversion
                    source_dt = localize_datetime(source_dt, source_tz)
                    target_dt = convert_datetime(source_dt, target)

                    # Create simple hour key in target timezone (no date information)
                    target_hour_str = f"{target_dt.hour:02d}:00"
                    
                    # Debug log to track the hour mapping
                    source_hour = getattr(source_dt, 'hour', hour if 'hour' in locals() else 0)
                    target_hour = target_dt.hour
                    
                    # Log the conversion happening - for any timezone, not just Europe
                    _LOGGER.info(f"Timezone conversion: {source_hour}:00 in {source_tz.key} → {target_hour}:00 in {target.key} with price {price}")

                    # Check if this hour key has already been processed
                    if target_hour_str in processed_hours:
                        # Handle DST transition - log it only at debug level
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(f"DST transition detected - hour {hour_str} ({source_timezone}) maps to already processed hour {target_hour_str}")

                        # Check if this is a new date (e.g., transition from 23:00 to 00:00)
                        if target_dt.date() != today_date:
                            # This is tomorrow's data, use a different key format to preserve it
                            tomorrow_key = f"tomorrow_{target_hour_str}"
                            converted[tomorrow_key] = price
                            continue
                    else:
                        processed_hours.add(target_hour_str)

                    # Store price with correct target hour - this is the critical assignment
                    converted[target_hour_str] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"Error converting hour {hour_str}: {e}")
                    converted[hour_str] = price  # Keep original in case of error

            return converted
        except Exception as e:
            _LOGGER.error(f"Error in convert_hourly_prices: {e}")
            # Return original prices in case of error
            return hourly_prices

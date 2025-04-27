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
        self.default_target_tz = get_timezone_object(default_target_tz) or dt_util.DEFAULT_TIME_ZONE

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

    def convert_hourly_prices(self, 
                             hourly_prices: Dict[str, float],
                             source_timezone_str: str, 
                             target_tz_str: Optional[str] = None,
                             today_date: Optional[date] = None) -> Dict[str, Dict[str, float]]:
        """Convert hourly prices dictionary keyed by ISO timestamps to target timezone.

        Args:
            hourly_prices: Dict mapping ISO timestamp strings to prices.
            source_timezone_str: Source timezone identifier string.
            target_tz_str: Target timezone identifier string (defaults to instance default).
            today_date: Optional specific date to use as reference for "today" (defaults to current date).

        Returns:
            Dict containing "today" and "tomorrow" keys, each holding a 
            dictionary mapping target timezone hour strings (HH:00) to prices.
            Example: {"today": {"00:00": 10.0, ...}, "tomorrow": {"00:00": 15.0, ...}}

        Raises:
            ValueError: If source_timezone is invalid.
        """
        if not hourly_prices:
            return {"today": {}, "tomorrow": {}}

        try:
            # Determine Timezones
            source_tz = get_timezone_object(source_timezone_str)
            if not source_tz:
                # If string is invalid, maybe it's a source identifier?
                source_tz_lookup = get_source_timezone(source_timezone_str)
                source_tz = get_timezone_object(source_tz_lookup)
                if not source_tz:
                    raise ValueError(f"Invalid source timezone identifier: {source_timezone_str}")
            
            # Determine target timezone object
            target_tz = None
            if target_tz_str:
                target_tz = get_timezone_object(target_tz_str)
            if not target_tz:
                target_tz = self.default_target_tz # Use instance default if needed
            
            _LOGGER.debug(f"Converting prices from {source_tz} to {target_tz}")

            # Determine Reference Date (Today in Target Timezone)
            # Use provided date or dt_util.now() for testability with freezegun
            today_target_date = today_date or dt_util.now(target_tz).date()
            tomorrow_target_date = today_target_date + timedelta(days=1)
            _LOGGER.debug(f"Reference date (today in target TZ {target_tz}): {today_target_date}")

            # Process Each Hour
            result = {"today": {}, "tomorrow": {}}
            processed_target_datetimes = set() # To detect DST fallbacks

            for iso_key, price in hourly_prices.items():
                if price is None: continue # Skip null prices

                try:
                    # Parse the ISO timestamp key
                    # Assume it includes offset, make aware UTC first for reliable conversion
                    # Correction: Parse directly, fromisoformat handles offsets.
                    source_dt_aware = datetime.fromisoformat(iso_key.replace("Z", "+00:00"))

                    # Convert to target timezone
                    target_dt = source_dt_aware.astimezone(target_tz)

                    # Determine target date and hour key
                    target_date = target_dt.date()
                    target_hour_key = f"{target_dt.hour:02d}:00"

                    # Check for DST fallback duplicate: same target hour but different source time
                    # We store the full target datetime to check
                    # Correction: Store tuple of (date, hour) for simpler check
                    target_dt_tuple = (target_date, target_dt.hour)
                    is_duplicate = target_dt_tuple in processed_target_datetimes
                    processed_target_datetimes.add(target_dt_tuple)

                    # Decide which dictionary to put it in
                    target_dict = None
                    if target_date == today_target_date:
                        target_dict = result["today"]
                    elif target_date == tomorrow_target_date:
                        target_dict = result["tomorrow"]
                    else:
                        # Belongs to a different day (e.g., day after tomorrow or yesterday)
                        # Log and skip for now, could be stored in "other" if needed
                        _LOGGER.debug(f"Skipping price for {iso_key} - maps to date {target_date} (ref: {today_target_date})")
                        continue

                    # Handle potential overwrites (e.g., DST fallback hour)
                    if target_hour_key in target_dict:
                        if is_duplicate:
                            # Handle potential DST fallback where the same hour might appear twice
                            _LOGGER.warning(
                                f"DST Fallback? Hour {target_hour_key} on {target_date} already exists. "
                                f"Input {iso_key} maps to this hour. Overwriting with later value."
                            )
                        else:
                            # This shouldn't happen unless input data is strange
                            _LOGGER.warning(f"Duplicate target hour key {target_hour_key} found for date {target_date}. "
                                            f"Input {iso_key} maps to this hour. Overwriting with later value.")

                    target_dict[target_hour_key] = price
                    # _LOGGER.debug(f"Mapped {iso_key} ({source_tz}) to {target_date} {target_hour_key} ({target_tz})")

                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"Error processing timestamp key '{iso_key}': {e}. Skipping price.")
                    continue # Skip this price

            # Log counts for verification
            _LOGGER.debug(f"Conversion result: {len(result['today'])} today prices, {len(result['tomorrow'])} tomorrow prices")
            return result

        except Exception as e:
            _LOGGER.error(f"Error in convert_hourly_prices: {e}", exc_info=True)
            # Return empty structure in case of major error
            return {"today": {}, "tomorrow": {}}

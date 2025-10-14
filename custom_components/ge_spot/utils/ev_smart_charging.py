"""Utility functions for EV Smart Charging integration compatibility."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Minimum number of intervals required for valid price data
# This prevents incomplete or invalid data from being exposed
MIN_VALID_INTERVALS = 12


def convert_to_ev_smart_format(
    interval_prices: Optional[Dict[str, float]],
    target_timezone: ZoneInfo,
    date_offset: int = 0
) -> List[Dict[str, Any]]:
    """Convert GE-Spot interval prices to EV Smart Charging format.

    Transforms the standard GE-Spot format (Dict[str, float] with HH:MM keys)
    into the format expected by EV Smart Charging integration
    (List[Dict[str, Any]] with datetime and value).

    Args:
        interval_prices: Dictionary mapping time strings (HH:MM) to prices.
                        Example: {"00:00": 120.50, "00:15": 121.00, ...}
        target_timezone: Target timezone for datetime objects (ZoneInfo instance).
        date_offset: Number of days to offset from today (0=today, 1=tomorrow).

    Returns:
        List of dictionaries with 'time' (datetime) and 'value' (float).
        Returns empty list if input is invalid or has fewer than MIN_VALID_INTERVALS items.

    Example:
        >>> from zoneinfo import ZoneInfo
        >>> prices = {"14:00": 123.45, "14:15": 124.00, ...}
        >>> tz = ZoneInfo("Europe/Stockholm")
        >>> result = convert_to_ev_smart_format(prices, tz, date_offset=0)
        >>> result[0]
        {'time': datetime(2023, 10, 29, 14, 0, 0, tzinfo=ZoneInfo('Europe/Stockholm')),
         'value': 123.45}
    """
    # Validate input
    if not isinstance(interval_prices, dict):
        _LOGGER.debug(
            "Invalid input type for EV Smart format conversion: expected dict, got %s",
            type(interval_prices).__name__
        )
        return []

    if len(interval_prices) < MIN_VALID_INTERVALS:
        _LOGGER.debug(
            "Insufficient intervals for EV Smart format: %d (minimum: %d)",
            len(interval_prices),
            MIN_VALID_INTERVALS
        )
        return []

    # Get base date in target timezone
    now = dt_util.now().astimezone(target_timezone)
    base_date = (now + timedelta(days=date_offset)).date()

    # Convert to EV Smart format
    result = []
    for time_key, price in interval_prices.items():
        try:
            # Parse HH:MM format
            if not isinstance(time_key, str) or ':' not in time_key:
                _LOGGER.debug(
                    "Skipping invalid time key format: %s (expected HH:MM)",
                    time_key
                )
                continue

            hour_str, minute_str = time_key.split(':', 1)
            hour = int(hour_str)
            minute = int(minute_str)

            # Validate hour and minute ranges
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                _LOGGER.debug(
                    "Skipping invalid time: %s (hour must be 0-23, minute 0-59)",
                    time_key
                )
                continue

            # Create timezone-aware datetime
            dt = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                hour,
                minute,
                0,
                tzinfo=target_timezone
            )

            # Round price to 4 decimal places
            rounded_price = round(float(price), 4)

            result.append({
                "time": dt,
                "value": rounded_price
            })

        except (ValueError, AttributeError, TypeError) as exc:
            _LOGGER.debug(
                "Failed to parse interval entry %s=%s: %s",
                time_key,
                price,
                exc
            )
            continue

    # Sort by time (earliest first)
    result.sort(key=lambda x: x["time"])

    _LOGGER.debug(
        "Converted %d intervals to EV Smart format (date_offset=%d, tz=%s)",
        len(result),
        date_offset,
        target_timezone
    )

    return result

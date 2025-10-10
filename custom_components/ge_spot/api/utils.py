"""Shared utility functions for API implementations."""
import asyncio
import logging
import datetime
from typing import Dict, Any, List
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..timezone import TimezoneService

_LOGGER = logging.getLogger(__name__)

# Cache timezone objects to avoid repeated initialization
@lru_cache(maxsize=32)
def get_timezone(tz_name):
    """Get timezone object with caching to avoid repeated initialization."""
    return ZoneInfo(tz_name)

async def fetch_with_retry(fetch_func, is_data_available, retry_interval=1800, end_time=None, local_tz_name=None, *args, **kwargs):
    """
    Repeatedly call fetch_func until is_data_available(result) is True or until end_time is reached.
    retry_interval is in seconds (default: 1800 = 30 minutes).
    end_time: a datetime.time object (e.g., time(23, 50)) in the local timezone.
    local_tz_name: string, e.g. 'Europe/Oslo', 'Europe/Berlin', etc.
    """
    import datetime
    attempts = 0

    # Create the timezone object outside the loop
    local_tz = None
    if local_tz_name:
        # Run the blocking call in an executor to avoid blocking the event loop
        local_tz = await asyncio.get_event_loop().run_in_executor(
            None, get_timezone, local_tz_name
        )

    while True:
        result = await fetch_func(*args, **kwargs)
        if is_data_available(result):
            _LOGGER.info(f"Successfully fetched data after {attempts+1} attempt(s).")
            return result
        if attempts == 0:
            _LOGGER.info(f"Data not available yet (first attempt). Will retry every {retry_interval//60} minutes until {end_time}.")
        attempts += 1
        # Check if we should stop
        if end_time and local_tz:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_local = now_utc.astimezone(local_tz)
            cutoff_dt = now_local.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
            if now_local >= cutoff_dt:
                _LOGGER.warning(f"Reached cutoff time {end_time} in {local_tz_name}. Stopping retry loop.")
                break
        await asyncio.sleep(retry_interval)
    _LOGGER.warning(f"Failed to fetch data before cutoff time. Proceeding without it.")
    return None

def get_now(reference_time=None, hass=None):
    """Get current time with consistent handling.

    Args:
        reference_time: Optional reference time to use instead of now
        hass: Optional Home Assistant instance for timezone handling

    Returns:
        A timezone-aware datetime object
    """
    if reference_time is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    else:
        now = reference_time

    # Convert to local time if Home Assistant instance provided
    if hass:
        tz_service = TimezoneService(hass)
        return tz_service.convert_to_target_timezone(now)

    return now

def format_result(data, source_name, currency):
    """Format API result with common metadata.

    Args:
        data: The processed data dictionary
        source_name: Name of the data source
        currency: Target currency

    Returns:
        Dictionary with added metadata
    """
    if not data:
        return None

    # Add standardized metadata
    data["data_source"] = source_name
    data["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["currency"] = currency

    return data

def check_prices_count(interval_prices):
    """Check if we have the expected number of interval prices.

    Args:
        interval_prices: Dictionary of interval prices

    Returns:
        True if count is reasonable, False otherwise
    """
    from ..const.time import TimeInterval
    expected_count = TimeInterval.get_intervals_per_day()

    if len(interval_prices) != expected_count and len(interval_prices) > 0:
        _LOGGER.warning(f"Expected {expected_count} interval prices, got {len(interval_prices)}. Prices may be incomplete.")
        return False
    return True


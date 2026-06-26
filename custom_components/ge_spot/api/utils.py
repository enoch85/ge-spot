"""Shared utility functions for API implementations."""

import asyncio
import logging
import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..const.network import Network

_LOGGER = logging.getLogger(__name__)


# Cache timezone objects to avoid repeated initialization
@lru_cache(maxsize=32)
def get_timezone(tz_name):
    """Get timezone object with caching to avoid repeated initialization."""
    return ZoneInfo(tz_name)


async def fetch_with_retry(
    fetch_func,
    is_data_available,
    retry_interval=Network.Defaults.STANDARD_UPDATE_INTERVAL_MINUTES
    * Network.Defaults.SECONDS_PER_MINUTE,
    end_time=None,
    local_tz_name=None,
    *args,
    **kwargs,
):
    """
    Repeatedly call fetch_func until is_data_available(result) is True or until end_time is reached.
    retry_interval is in seconds (default: STANDARD_UPDATE_INTERVAL_MINUTES * SECONDS_PER_MINUTE = 30 minutes).
    end_time: a datetime.time object (e.g. time(RETRY_CUTOFF_TIME_HOUR, RETRY_CUTOFF_TIME_MINUTE)) in the local timezone.
    local_tz_name: string, e.g. 'Europe/Oslo', 'Europe/Berlin', etc.
    """
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

        # Check if result indicates "data not ready yet" (HTTP 204)
        if result and isinstance(result, dict) and result.get("status") == 204:
            if attempts == 0:
                _LOGGER.info(
                    f"Data not yet published (HTTP 204). Will retry every {retry_interval//60} minutes until {end_time}."
                )
            attempts += 1
        elif is_data_available(result):
            _LOGGER.info(f"Successfully fetched data after {attempts+1} attempt(s).")
            return result
        else:
            if attempts == 0:
                _LOGGER.info(
                    f"Data not available yet (first attempt). Will retry every {retry_interval//60} minutes until {end_time}."
                )
            attempts += 1

        # Check if we should stop
        if end_time and local_tz:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_local = now_utc.astimezone(local_tz)
            cutoff_dt = now_local.replace(
                hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0
            )
            if now_local >= cutoff_dt:
                _LOGGER.warning(
                    f"Reached cutoff time {end_time} in {local_tz_name}. Stopping retry loop."
                )
                break
        await asyncio.sleep(retry_interval)
    _LOGGER.warning(f"Failed to fetch data before cutoff time. Proceeding without it.")
    return None

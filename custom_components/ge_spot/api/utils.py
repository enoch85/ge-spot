"""Shared utility functions for API implementations."""
import logging
import datetime
from typing import Dict, Any, List

from ..timezone import TimezoneService

_LOGGER = logging.getLogger(__name__)

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
        return tz_service.convert_to_ha_timezone(now)

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

def check_prices_count(hourly_prices):
    """Check if we have the expected 24 hourly prices.

    Args:
        hourly_prices: Dictionary of hourly prices

    Returns:
        True if count is correct, False otherwise
    """
    if len(hourly_prices) != 24 and len(hourly_prices) > 0:
        _LOGGER.warning(f"Expected 24 hourly prices, got {len(hourly_prices)}. Prices may be incomplete.")
        return False
    return True

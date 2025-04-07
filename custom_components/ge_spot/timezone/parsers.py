"""Date and time parsing utilities."""
import logging
from datetime import datetime
from typing import Union

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

def parse_datetime(timestamp: Union[str, datetime]) -> datetime:
    """Parse various timestamp formats into a consistent datetime object.

    Handles various API timestamp formats:
    - ISO format with Z suffix
    - ISO format with explicit offset
    - ISO format without timezone
    - Already a datetime object
    """
    # Already a datetime object
    if isinstance(timestamp, datetime):
        # Ensure it's timezone aware
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=dt_util.UTC)
        return timestamp

    if not timestamp:
        return dt_util.now()

    try:
        # Handle UTC indicator (Z)
        if isinstance(timestamp, str) and timestamp.endswith('Z'):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            _LOGGER.debug(f"Parsed UTC timestamp: {timestamp} → {dt.isoformat()}")
            return dt

        # Handle explicit timezone offset or standard ISO format
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp)

            # Add UTC timezone if not provided
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=dt_util.UTC)

            return dt

    except (ValueError, TypeError) as e:
        # Try HA's parser as fallback
        try:
            dt = dt_util.parse_datetime(timestamp)
            if dt:
                return dt
        except Exception:
            pass

        _LOGGER.error(f"Error parsing datetime {timestamp}: {e}")

    # Default fallback
    return dt_util.now()

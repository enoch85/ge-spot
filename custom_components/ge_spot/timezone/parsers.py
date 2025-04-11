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
        if isinstance(timestamp, str):
            original_timestamp = timestamp
            
            # Handle UTC indicator (Z)
            if timestamp.endswith('Z'):
                timestamp = timestamp.replace('Z', '+00:00')
            
            # Try parsing with built-in fromisoformat
            try:
                dt = datetime.fromisoformat(timestamp)
                
                # Add UTC timezone if not provided
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=dt_util.UTC)
                    _LOGGER.debug(f"Added UTC timezone to naive datetime: {original_timestamp} → {dt.isoformat()}")
                else:
                    _LOGGER.debug(f"Parsed timezone-aware timestamp: {original_timestamp} → {dt.isoformat()}")
                
                return dt
            except ValueError:
                # Try more format patterns if fromisoformat fails
                pass

            # Try common alternative formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S",  # ISO without timezone
                "%Y-%m-%dT%H:%M",      # ISO without seconds or timezone
                "%Y-%m-%d %H:%M:%S",   # Space separator
                "%Y-%m-%d %H:%M",      # Space separator without seconds
                "%Y%m%d%H%M%S",        # Compact format (ENTSOE)
                "%Y%m%d%H%M"           # Compact format without seconds
            ]:
                try:
                    dt = datetime.strptime(timestamp, fmt)
                    dt = dt.replace(tzinfo=dt_util.UTC)
                    _LOGGER.debug(f"Parsed timestamp with format {fmt}: {original_timestamp} → {dt.isoformat()}")
                    return dt
                except ValueError:
                    continue

        # If we get here, try HA's parser as fallback
        dt = dt_util.parse_datetime(timestamp)
        if dt:
            _LOGGER.debug(f"Parsed timestamp using HA parser: {timestamp} → {dt.isoformat()}")
            return dt

    except Exception as e:
        _LOGGER.error(f"Error parsing datetime {timestamp}: {e}")

    # Default fallback - this should be avoided if possible
    _LOGGER.warning(f"Failed to parse timestamp '{timestamp}', using current time as fallback")
    return dt_util.now()

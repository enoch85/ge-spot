"""Timezone utility functions to avoid circular imports."""
import logging
from datetime import datetime, tzinfo, timedelta
from typing import Dict, Any, Optional, Union

import zoneinfo

from ..const.sources import Source
from ..const.time import TimezoneConstants, TimezoneName
from ..const.api import SourceTimezone
from ..const.areas import Timezone

_LOGGER = logging.getLogger(__name__)

def get_timezone_by_name(timezone_name: str) -> str:
    """Get timezone identifier for a given name or area.
    
    Args:
        timezone_name: Timezone name or area code
        
    Returns:
        Timezone identifier (IANA format)
    """
    # Check if it's a direct timezone identifier already (contains a '/')
    if "/" in timezone_name:
        return timezone_name
        
    # Check if it's in the area timezones mapping
    if timezone_name in Timezone.AREA_TIMEZONES:
        return Timezone.AREA_TIMEZONES[timezone_name]
        
    # Check if it's a known timezone name that can be mapped
    iana_name = TimezoneName.get_iana_name(timezone_name)
    if iana_name != timezone_name:  # If mapping occurred
        return iana_name
        
    # Fallback
    _LOGGER.warning("Could not resolve timezone for name: %s, using default", timezone_name)
    return TimezoneConstants.DEFAULT_FALLBACK

def get_source_timezone(source: str, area: Optional[str] = None) -> str:
    """Get timezone for a specific API source.

    Args:
        source: Source identifier
        area: Optional area code

    Returns:
        Timezone string
    """
    if source in SourceTimezone.API_TIMEZONES:
        tz = SourceTimezone.API_TIMEZONES.get(source)
        _LOGGER.debug(f"Found timezone {tz} for source {source}")
        return tz

    # If source is not a recognized Source constant, it might be a direct timezone string
    if "/" in source:  # Looks like a timezone string (e.g., "Europe/Berlin")
        return source

    # Log clear error but return fallback
    _LOGGER.error(f"No timezone definition found for source: {source}")
    return TimezoneConstants.DEFAULT_FALLBACK

def get_source_format(source: str) -> Optional[str]:
    """Get datetime format for a specific API source.

    Args:
        source: Source identifier

    Returns:
        Format string or None if not defined
    """
    format_str = SourceTimezone.API_FORMATS.get(source)

    if not format_str:
        _LOGGER.debug(f"No specific datetime format defined for source: {source}")

    return format_str

def get_timezone_object(timezone_id: str) -> tzinfo:
    """Get timezone object for a timezone ID.

    Args:
        timezone_id: Timezone identifier

    Returns:
        Timezone object

    Raises:
        ValueError: If timezone_id is invalid or cannot be resolved
    """
    # Handle case where timezone_id is already a ZoneInfo object
    if isinstance(timezone_id, zoneinfo.ZoneInfo):
        return timezone_id

    # Special case for UTC
    if timezone_id == "UTC":
        import datetime
        return datetime.timezone.utc

    # Convert common timezone names to IANA names
    iana_timezone_id = TimezoneName.get_iana_name(timezone_id)

    try:
        return zoneinfo.ZoneInfo(iana_timezone_id)
    except Exception as e:
        error_msg = f"Failed to get timezone object for {timezone_id} (as {iana_timezone_id}): {e}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)

def convert_datetime(dt: datetime, target_tz: Union[str, tzinfo], source_tz: Optional[Union[str, tzinfo]] = None) -> datetime:
    """Convert datetime between timezones.

    Args:
        dt: Datetime to convert
        target_tz: Target timezone (string or tzinfo)
        source_tz: Source timezone (string or tzinfo), required if dt is naive

    Returns:
        Converted datetime

    Raises:
        ValueError: If dt is naive and no source_tz provided, or if timezone is invalid
    """
    # Handle target timezone
    if isinstance(target_tz, str):
        try:
            target_tz = get_timezone_object(target_tz)
        except ValueError as e:
            error_msg = f"Invalid target timezone for conversion: {e}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg) from e

    # Handle naive datetime
    if dt.tzinfo is None:
        if source_tz:
            # Handle string timezone
            if isinstance(source_tz, str):
                try:
                    source_tz = get_timezone_object(source_tz)
                except ValueError as e:
                    error_msg = f"Invalid source timezone for conversion: {e}"
                    _LOGGER.error(error_msg)
                    raise ValueError(error_msg) from e

            # Make datetime timezone-aware
            dt = dt.replace(tzinfo=source_tz)
        else:
            # Cannot proceed without source timezone for naive datetime
            error_msg = f"Cannot convert naive datetime {dt} without source timezone"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

    # Convert to target timezone
    return dt.astimezone(target_tz)

def localize_datetime(dt: datetime, timezone_id: str) -> datetime:
    """Localize a naive datetime to a timezone.

    Args:
        dt: Naive datetime
        timezone_id: Timezone identifier

    Returns:
        Localized datetime

    Raises:
        ValueError: If timezone_id is invalid
    """
    try:
        tz = get_timezone_object(timezone_id)
    except ValueError as e:
        error_msg = f"Invalid timezone for localization: {e}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg) from e

    if dt.tzinfo is not None:
        return dt.astimezone(tz)

    return dt.replace(tzinfo=tz)


def normalize_hour_value(hour: int, base_date: datetime.date) -> tuple[int, datetime.date]:
    """Normalize hour values that may be outside the 0-23 range.

    This handles special cases like 24:00 (midnight of next day),
    or values like 25-47 that represent hours of the next day.

    Args:
        hour: Hour value, which may be outside the 0-23 range
        base_date: Base date to use for calculations

    Returns:
        Tuple of (normalized_hour, adjusted_date)
    """
    days_to_add = 0
    normalized_hour = hour

    if hour == 24:
        # 24:00 represents midnight of the next day
        normalized_hour = 0
        days_to_add = 1
    elif hour > 24 and hour < 48:
        # Some systems use 25-47 to represent hours of the next day
        normalized_hour = hour - 24
        days_to_add = 1
    elif hour >= 48 and hour < 72:
        # Some systems use 48-71 to represent hours of day after next
        normalized_hour = hour - 48
        days_to_add = 2
    elif hour >= 72 or hour < 0:
        # Handle truly invalid hours
        raise ValueError(f"Hour value {hour} is outside the supported range")

    # Apply the date adjustment
    adjusted_date = base_date
    if days_to_add > 0:
        adjusted_date = base_date + timedelta(days=days_to_add)

    return normalized_hour, adjusted_date

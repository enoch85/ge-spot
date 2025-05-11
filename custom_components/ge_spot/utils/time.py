from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import logging

# If pytz is a strict requirement and used elsewhere for timezone objects:
# import pytz 
# Otherwise, for Python 3.9+ zoneinfo is preferred for IANA timezone names.
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO_FORMAT_NO_OFFSET = "%Y-%m-%dT%H:%M:%S"
ISO_FORMAT_WITH_Z = "%Y-%m-%dT%H:%M:%SZ"
ISO_FORMAT_WITH_OFFSET = "%Y-%m-%dT%H:%M:%S%z"
ISO_FORMAT_WITH_COLON_OFFSET = "%Y-%m-%dT%H:%M:%S%:z" # For parsing offsets like +02:00

_LOGGER = logging.getLogger(__name__)

def parse_iso_datetime_with_fallback(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string with or without timezone information.

    Handles formats like:
    - "YYYY-MM-DDTHH:MM:SSZ" (UTC)
    - "YYYY-MM-DDTHH:MM:SS+HH:MM" (with offset)
    - "YYYY-MM-DDTHH:MM:SS+HHMM" (with offset, no colon)
    - "YYYY-MM-DDTHH:MM:SS" (naive, assumed UTC or to be localized later)

    Returns a timezone-aware datetime object if timezone info is present,
    otherwise a naive datetime object.
    """
    if not dt_str:
        return None

    formats_to_try = [
        ISO_FORMAT_WITH_COLON_OFFSET, # Try first for common format like +01:00
        ISO_FORMAT_WITH_OFFSET,       # For +0100
        ISO_FORMAT_WITH_Z,            # For Zulu time (UTC)
        ISO_FORMAT_NO_OFFSET          # For naive datetime
    ]

    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(dt_str, fmt)
            # If the format is ISO_FORMAT_WITH_Z, it's UTC
            if fmt == ISO_FORMAT_WITH_Z:
                return dt.replace(tzinfo=timezone.utc)
            # If the format parsed a timezone offset (strptime with %z or %:z makes it aware)
            # or if it was ISO_FORMAT_NO_OFFSET (naive), it's returned as is.
            # For naive, the caller must decide the timezone.
            return dt
        except ValueError:
            continue

    # Attempt to handle cases where offset might not have colon, e.g. "+0200"
    # Python's %z handles this, but if there are other subtle variations:
    # For example, if the string has milliseconds, like "YYYY-MM-DDTHH:MM:SS.sssZ"
    if '.' in dt_str:
        try:
            dt_naive_str = dt_str.split('.')[0]
            # Check for Z at the end
            if dt_str.endswith('Z'):
                dt = datetime.strptime(dt_naive_str, ISO_FORMAT_NO_OFFSET)
                return dt.replace(tzinfo=timezone.utc)
            # Check for offset like +HH:MM or +HHMM at the end
            # This part is more complex if the offset format varies greatly
            # For simplicity, we rely on the main loop for common offset formats.
            # If a specific non-standard offset format is common, add it to formats_to_try.
        except ValueError:
            pass # Fall through if microsecond parsing fails

    _LOGGER.warning("Could not parse datetime string: %s with known ISO formats.", dt_str)
    return None

def get_area_timezone(area_code: str, default_tz: str = "UTC") -> ZoneInfo:
    """Get the ZoneInfo object for a given area code.
    
    This is a placeholder. In a real scenario, you'd have a mapping from
    area_code (e.g., "SE3", "DE-LU") to IANA timezone names (e.g., "Europe/Stockholm").
    For now, it attempts to use the area_code directly if it resembles a tz name,
    otherwise defaults.
    """
    try:
        # A more robust solution would use a predefined map: AREA_TO_TZ_MAP.get(area_code, default_tz)
        # Example: if area_code is "Europe/Berlin" or similar, it might work directly.
        return ZoneInfo(area_code)
    except ZoneInfoNotFoundError:
        _LOGGER.debug("Timezone for area code '%s' not found directly. Using default: %s", area_code, default_tz)
        try:
            return ZoneInfo(default_tz)
        except ZoneInfoNotFoundError:
            _LOGGER.error("Default timezone '%s' also not found. Falling back to UTC.", default_tz)
            return ZoneInfo("UTC") # Fallback to UTC if default is also invalid

# Example of a potential mapping (to be defined in const/time.py or areas.py)
# AREA_TIMEZONE_MAP = {
#     "SE1": "Europe/Stockholm",
#     "SE2": "Europe/Stockholm",
#     "SE3": "Europe/Stockholm",
#     "SE4": "Europe/Stockholm",
#     "FI": "Europe/Helsinki",
#     "DK1": "Europe/Copenhagen",
#     "DK2": "Europe/Copenhagen",
#     "DE-LU": "Europe/Berlin",
#     "AT": "Europe/Vienna",
#     # ... and so on for all supported areas
# }


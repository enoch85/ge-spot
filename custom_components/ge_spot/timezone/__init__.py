"""Timezone utilities for handling datetime conversions."""
# Re-export the core classes
from .service import TimezoneService
from .parser import TimestampParser
from .converter import TimezoneConverter
from .dst_handler import DSTHandler
from .hour_calculator import HourCalculator

# Re-export only necessary functions from source_tz
from .source_tz import get_source_timezone, get_timezone_object

# Add get_timezone_for_area function
from ..const.areas import Timezone

def get_timezone_for_area(area: str) -> str:
    """Get timezone string for a specific area.
    
    Args:
        area: The area code to get timezone for
        
    Returns:
        Timezone string (e.g., 'Europe/Oslo')
    """
    return Timezone.AREA_TIMEZONES.get(area)

# Export everything needed by other modules
__all__ = [
    # Main service (primary interface)
    "TimezoneService",

    # Component classes
    "TimestampParser",
    "TimezoneConverter",
    "DSTHandler",
    "HourCalculator",

    # Supporting functions
    "get_source_timezone",
    "get_timezone_object",

    # New additions
    "get_timezone_for_area",
]

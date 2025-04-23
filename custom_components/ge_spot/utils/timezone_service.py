"""Re-export of the TimezoneService from timezone module for backward compatibility."""
from ..timezone.service import TimezoneService
from ..timezone import get_timezone_for_area

# Re-export main class and functions
__all__ = [
    "TimezoneService",
    "get_timezone_for_area",
]
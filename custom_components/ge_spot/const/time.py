"""Time-related constants for GE-Spot integration."""

class TimeInterval:
    """Time interval constants."""
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"
    DAILY = "P1D"
    
    DEFAULT = HOURLY

class TimeFormat:
    """Time format constants."""
    HOUR_ONLY = "%H:00"
    HOUR_MINUTE = "%H:%M"
    DATE_ONLY = "%Y-%m-%d"
    DATE_HOUR = "%Y-%m-%dT%H%M%S"
    ENTSOE_DATE_HOUR = "%Y%m%d%H%M"

class PeriodType:
    """Period types for price data."""
    TODAY = "today"
    TOMORROW = "tomorrow"
    OTHER = "other"
    
    MIN_VALID_HOURS = 20  # Minimum hours required for valid data

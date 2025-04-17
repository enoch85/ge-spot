"""Time and timezone-related constants for GE-Spot integration."""

class TimezoneName:
    """IANA timezone name constants."""
    # Standard timezone identifiers
    UTC = "Etc/UTC"
    EUROPE_COPENHAGEN = "Europe/Copenhagen"
    EUROPE_PARIS = "Europe/Paris"
    EUROPE_MADRID = "Europe/Madrid"
    AUSTRALIA_SYDNEY = "Australia/Sydney"
    AMERICA_CHICAGO = "America/Chicago"

    # Mapping of common names to IANA names
    COMMON_TO_IANA = {
        "UTC": UTC,
        "GMT": UTC,
        "CET": "Europe/Paris",
        "CEST": "Europe/Paris",
    }

    @staticmethod
    def get_iana_name(timezone_id):
        """Convert common timezone name to IANA name if needed."""
        if timezone_id in TimezoneName.COMMON_TO_IANA:
            return TimezoneName.COMMON_TO_IANA[timezone_id]
        return timezone_id

class TimezoneReference:
    """Timezone reference options."""
    LOCAL_AREA = "local_area"
    HOME_ASSISTANT = "home_assistant"

    OPTIONS = {
        HOME_ASSISTANT: "Home Assistant Time (show prices for your current hour)",
        LOCAL_AREA: "Local Area Time (show prices for each area's current hour)"
    }

    DEFAULT = HOME_ASSISTANT  # Default to Home Assistant Time as requested

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

class DSTTransitionType:
    """DST transition type constants."""
    SPRING_FORWARD = "spring_forward"  # When clocks move forward (lose 1 hour)
    FALL_BACK = "fall_back"  # When clocks move backward (gain 1 hour)

class TimezoneConstants:
    """Timezone-related constants."""
    # Default fallback timezone
    DEFAULT_FALLBACK = "INVALID_TIMEZONE"  # Use an invalid value to force explicit error

    # API metadata keys that might contain timezone information
    METADATA_KEYS = ["timezone", "time_zone", "api_timezone", "timeZone"]

    # Timezone conversion options
    CONVERSION_OPTIONS = {
        "replace_only": False,   # When True, only replace timezone without conversion
        "preserve_dst": True,    # Preserve DST information during conversion
        "fallback_to_utc": False # Do NOT use UTC as fallback if timezone not found
    }

    # DST handling options
    DST_OPTIONS = {
        "spring_forward_skip": True,  # Skip non-existent hours during spring forward
        "fall_back_first": True       # Use first occurrence during ambiguous fall back hours
    }

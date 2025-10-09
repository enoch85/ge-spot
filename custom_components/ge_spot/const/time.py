"""Time and timezone-related constants for GE-Spot integration."""

class TimezoneName:
    """IANA timezone name constants."""
    # Standard timezone identifiers
    UTC = "Etc/UTC"
    EUROPE_COPENHAGEN = "Europe/Copenhagen"
    EUROPE_PARIS = "Europe/Paris"
    EUROPE_MADRID = "Europe/Madrid"
    EUROPE_OSLO = "Europe/Oslo"
    EUROPE_BERLIN = "Europe/Berlin"
    EUROPE_LISBON = "Europe/Lisbon"
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

    DEFAULT = LOCAL_AREA  # Default to Local Area Time for more intuitive behavior

class TimeInterval:
    """Time interval constants."""
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"
    DAILY = "P1D"

    DEFAULT = QUARTER_HOURLY

    @staticmethod
    def get_interval_minutes() -> int:
        """Get interval duration in minutes."""
        if TimeInterval.DEFAULT == TimeInterval.QUARTER_HOURLY:
            return 15
        elif TimeInterval.DEFAULT == TimeInterval.HOURLY:
            return 60
        return 15
    
    @staticmethod
    def get_interval_seconds() -> int:
        """Get interval duration in seconds."""
        return TimeInterval.get_interval_minutes() * 60

    @staticmethod
    def get_intervals_per_hour() -> int:
        """Get number of intervals per hour."""
        return 60 // TimeInterval.get_interval_minutes()

    @staticmethod
    def get_intervals_per_day() -> int:
        """Get number of intervals per day."""
        return 24 * TimeInterval.get_intervals_per_hour()

    @staticmethod
    def get_intervals_per_day_dst_spring() -> int:
        """Get intervals for DST spring forward day (lose 1 hour)."""
        return TimeInterval.get_intervals_per_day() - TimeInterval.get_intervals_per_hour()

    @staticmethod
    def get_intervals_per_day_dst_fall() -> int:
        """Get intervals for DST fall back day (gain 1 hour)."""
        return TimeInterval.get_intervals_per_day() + TimeInterval.get_intervals_per_hour()

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

    MIN_VALID_INTERVALS = 80  # Minimum intervals required for valid data (80 of 96 = 83%)

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

class ValidationRetry:
    """Constants for background validation retry logic."""
    # Daily retry timing (seconds)
    MAX_RANDOM_DELAY_SECONDS = 3600  # Random delay up to 1 hour within retry window
    RETRY_CHECK_INTERVAL_SECONDS = 1800  # Check every 30 minutes if should retry


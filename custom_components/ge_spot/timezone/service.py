"""Main timezone service coordinating all timezone operations."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pytz

# Home Assistant imports
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

# Local imports
# Import Timezone class instead of AREA_TIMEZONES directly
from ..const.areas import Area, Timezone
from ..const.config import Config
from ..const.time import TimezoneConstants, TimezoneReference, TimeInterval
from .timezone_converter import TimezoneConverter
from .dst_handler import DSTHandler
from .interval_calculator import IntervalCalculator
from .parser import TimestampParser
from .timezone_utils import get_source_timezone, get_timezone_object


_LOGGER = logging.getLogger(__name__)

class TimezoneService:
    """Service for unified timezone handling across the integration."""

    def __init__(self, hass: Optional[HomeAssistant] = None, area: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional Home Assistant instance, area, and config."""
        self.hass = hass
        self.area = area
        self.config = config or {}

        # Always store system timezone for reference
        self.system_timezone = dt_util.get_time_zone(hass.config.time_zone) if hass else dt_util.DEFAULT_TIME_ZONE

        # Get area timezone if available
        self.area_timezone = None
        # Use Timezone.AREA_TIMEZONES
        if area and area in Timezone.AREA_TIMEZONES:
            area_tz_str = Timezone.AREA_TIMEZONES[area]
            self.area_timezone = get_timezone_object(area_tz_str)
            if self.area_timezone:
                _LOGGER.debug(f"Using area-specific timezone {area_tz_str} for {area}")
            else:
                _LOGGER.warning(f"Failed to get timezone object for {area_tz_str}, falling back to system timezone")

        # For UI consistency, use system timezone as the default target timezone
        self.ha_timezone = self.system_timezone

        # Get timezone reference from config
        self.timezone_reference = self.config.get(Config.TIMEZONE_REFERENCE, TimezoneReference.DEFAULT)

        # Determine the effective target timezone based on the reference
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            self.target_timezone = self.area_timezone
            _LOGGER.debug(f"Effective target timezone set to AREA timezone: {self.target_timezone}")
        else:
            self.target_timezone = self.ha_timezone # Default to HA timezone
            _LOGGER.debug(f"Effective target timezone set to HA timezone: {self.target_timezone}")


        # Initialize component classes
        self.parser = TimestampParser()
        # Pass self (the TimezoneService instance) to the converter
        self.converter = TimezoneConverter(self)
        self.dst_handler = DSTHandler(self.target_timezone) # Use target_timezone for DST handler

        # Determine which timezone to use for interval calculation based on the timezone reference
        # IntervalCalculator needs the reference mode to decide internally
        self.interval_calculator = IntervalCalculator(
            timezone=self.target_timezone, # Pass the determined target timezone
            system_timezone=self.system_timezone,
            area_timezone=self.area_timezone,
            timezone_reference=self.timezone_reference
        )

        _LOGGER.debug(f"Initialized timezone service. System TZ: {self.system_timezone}, " +
                    (f"Area TZ: {self.area_timezone}, " if self.area_timezone else "") +
                    f"HA TZ: {self.ha_timezone}, Target TZ: {self.target_timezone}, " +
                    f"Reference Mode: {self.timezone_reference}")

    def extract_source_timezone(self, api_data: Dict[str, Any], source_type: str) -> str:
        """Extract timezone from API data or fall back to constants.

        Args:
            api_data: The raw API response data
            source_type: The API source identifier

        Returns:
            Timezone string (e.g., 'Europe/Oslo')
        """
        # Try to get from response metadata
        if isinstance(api_data, dict):
            for key in TimezoneConstants.METADATA_KEYS:
                if key in api_data and api_data[key]:
                    tz = api_data[key]
                    _LOGGER.debug(f"Using timezone from API data ({key}): {tz}")
                    return tz

        # Fall back to constants - this should always work since we define constants for all sources
        tz = get_source_timezone(source_type)
        if not tz or tz == TimezoneConstants.DEFAULT_FALLBACK:
            error_msg = f"Failed to determine source timezone for {source_type}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        _LOGGER.debug(f"Using timezone from constants for {source_type}: {tz}")
        return tz

    def parse_timestamp(self, timestamp_str, source_timezone):
        """Parse timestamp string using the timestamp parser.

        Args:
            timestamp_str: The timestamp string to parse
            source_timezone: The source timezone to use

        Returns:
            Parsed datetime object

        Raises:
            ValueError: If timestamp cannot be parsed
        """
        # Ensure we have a valid source_timezone
        if not source_timezone or source_timezone == TimezoneConstants.DEFAULT_FALLBACK:
            error_msg = f"Invalid source timezone provided: {source_timezone}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        return self.parser.parse(timestamp_str, source_timezone)

    def convert_to_ha_timezone(self, dt):
        """Convert datetime to Home Assistant timezone.
        DEPRECATED - Use convert_to_target_timezone for clarity.
        Kept for backward compatibility if needed, but should be phased out.
        """
        _LOGGER.warning("convert_to_ha_timezone is deprecated. Use convert_to_target_timezone.")
        return self.convert_to_target_timezone(dt)

    def convert_to_target_timezone(self, dt):
        """Convert datetime to the effective target timezone (HA or Area).

        Args:
            dt: The datetime to convert

        Returns:
            Converted datetime
        """
        # Ensure dt has a timezone
        if dt.tzinfo is None:
            error_msg = "Cannot convert naive datetime without source timezone"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Use the converter initialized with the target_timezone
        return self.converter.convert(dt, self.target_timezone)


    def normalize_interval_prices(self, interval_prices: Dict[str, float], source_tz_str: Optional[str] = None, is_five_minute: bool = False) -> Dict[datetime, float]:
        """Normalizes price timestamps to the target timezone, optionally using a source timezone hint and handling 5-minute intervals.
        
        Args:
            interval_prices: Dictionary of prices with timestamp keys
            source_tz_str: Optional source timezone hint
            is_five_minute: Whether data is in 5-minute intervals
            
        Returns:
            Dictionary with normalized datetime keys
        """
        _LOGGER.debug(
            "Normalizing %d price timestamps using target timezone: %s%s%s",
            len(interval_prices),
            self.target_timezone,
            f" (with source hint: {source_tz_str})" if source_tz_str else "",
            " (5-minute intervals)" if is_five_minute else " (standard intervals)"
        )
        normalized_prices = {}

        for timestamp_str, price in interval_prices.items():
            try:
                aware_dt = self._parse_timestamp(timestamp_str, source_hint=source_tz_str)

                if aware_dt is None:
                    _LOGGER.warning("Could not parse timestamp '%s', skipping.", timestamp_str)
                    continue

                target_dt = aware_dt.astimezone(self.target_timezone)

                # Align to the start of the interval (hour or 5-minute)
                if is_five_minute:
                    # For 5-minute data, keep the original minute, just zero out seconds/microseconds
                    aligned_dt = target_dt.replace(second=0, microsecond=0)
                else:
                    # For hourly data, align to the start of the hour
                    aligned_dt = target_dt.replace(minute=0, second=0, microsecond=0)

                normalized_prices[aligned_dt] = price

            except (ValueError, TypeError, pytz.exceptions.UnknownTimeZoneError) as e:
                _LOGGER.error("Error normalizing timestamp '%s': %s", timestamp_str, e)

        _LOGGER.debug("Successfully normalized %d timestamps.", len(normalized_prices))
        return normalized_prices

    # Example helper method (adapt based on actual parsing needs)
    def _parse_timestamp(self, timestamp_str: str, source_hint: Optional[str] = None) -> Optional[datetime]:
        """Parses a timestamp string into a timezone-aware datetime object, using hint if naive."""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None: # Check if naive
                source_tz = None
                if source_hint:
                    try:
                        source_tz = pytz.timezone(source_hint)
                    except pytz.exceptions.UnknownTimeZoneError:
                        _LOGGER.warning("Invalid source timezone hint '%s', ignoring.", source_hint)

                if source_tz:
                     # Localize naive timestamp with hint
                    dt = source_tz.localize(dt)
                    _LOGGER.debug("Localized naive timestamp '%s' using hint '%s'", timestamp_str, source_hint)
                else:
                    # Fallback: Assume UTC if no hint and naive
                    _LOGGER.debug("Timestamp '%s' is naive and no valid source hint provided, assuming UTC.", timestamp_str)
                    dt = pytz.utc.localize(dt)

            # Ensure the result is timezone-aware and in UTC for consistency before target conversion
            return dt.astimezone(pytz.utc)

        except ValueError:
            _LOGGER.error("Could not parse ISO format timestamp: %s", timestamp_str)
            # Consider adding handling for other potential formats if needed
            return None
        except Exception as e:
            _LOGGER.error("Unexpected error parsing timestamp '%s': %s", timestamp_str, e)
            return None

    def get_current_hour_key(self):
        """Get the current interval key in the appropriate timezone based on the timezone reference setting."""
        # Get current time in different timezones for debugging
        # Use pytz.utc instead of undefined timezone.utc
        now_utc = datetime.now(pytz.utc)
        now_ha = datetime.now(self.ha_timezone)
        now_area = datetime.now(self.area_timezone) if self.area_timezone else None

        # Fix typo: now_tc -> now_utc
        _LOGGER.debug(f"Current time - UTC: {now_utc.strftime('%H:%M:%S')}, HA: {now_ha.strftime('%H:%M:%S')}" +
                     (f", Area ({self.area}): {now_area.strftime('%H:%M:%S')}" if now_area else ""))

        interval_key = self.interval_calculator.get_current_interval_key()

        # Log which timezone is being used based on the timezone reference setting
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            used_tz = self.area_timezone
            _LOGGER.debug(f"Using area timezone {used_tz} for interval key (Local Area Time mode)")
        else:
            used_tz = self.ha_timezone
            _LOGGER.debug(f"Using HA timezone {used_tz} for interval key (Home Assistant Time mode)")

        _LOGGER.debug(f"Current interval key from calculator: {interval_key} (timezone: {used_tz}, area: {self.area})")
        return interval_key

    def get_current_interval_key(self):
        """Get the current interval key - alias for get_current_hour_key for consistency."""
        return self.get_current_hour_key()

    def is_dst_transition_day(self, dt=None):
        """Check if today is a DST transition day."""
        return self.dst_handler.is_dst_transition_day(dt)

    def get_next_hour_key(self) -> str:
        """Get key for the next interval in target timezone.

        Returns:
            String key in format HH:MM
        """
        # Delegate to interval calculator for consistent handling
        now = dt_util.now()
        interval_minutes = TimeInterval.get_interval_minutes()
        next_interval = now + timedelta(minutes=interval_minutes)

        # Use the interval calculator for consistent timezone handling based on timezone_reference
        return self.interval_calculator.get_interval_key_for_datetime(next_interval)

    def get_next_interval_key(self) -> str:
        """Get key for the next interval - alias for get_next_hour_key for consistency."""
        return self.get_next_hour_key()

    def get_today_range(self) -> List[str]:
        """Get list of interval keys for today."""
        # Generate all intervals for the day based on configured interval duration
        interval_minutes = TimeInterval.get_interval_minutes()
        intervals_per_hour = TimeInterval.get_intervals_per_hour()
        result = []
        for hour in range(24):
            for i in range(intervals_per_hour):
                minute = i * interval_minutes
                result.append(f"{hour:02d}:{minute:02d}")
        return result

    def get_tomorrow_range(self) -> List[str]:
        """Get list of interval keys for tomorrow."""
        # Same as today but represents tomorrow's intervals
        interval_minutes = TimeInterval.get_interval_minutes()
        intervals_per_hour = TimeInterval.get_intervals_per_hour()
        result = []
        for hour in range(24):
            for i in range(intervals_per_hour):
                minute = i * interval_minutes
                result.append(f"{hour:02d}:{minute:02d}")
        return result

"""Main timezone service coordinating all timezone operations."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant

from .parser import TimestampParser
from .converter import TimezoneConverter
from .dst_handler import DSTHandler
from .hour_calculator import HourCalculator
from .source_tz import get_source_timezone, get_timezone_object
from ..const.time import TimezoneConstants, TimezoneReference
from ..const.api import SourceTimezone
from ..const.areas import Timezone
from ..const.config import Config

_LOGGER = logging.getLogger(__name__)

class TimezoneService:
    """Service for unified timezone handling across the integration.""" # Corrected docstring quotes

    def __init__(self, hass: Optional[HomeAssistant] = None, area: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional Home Assistant instance, area, and config.""" # Corrected docstring quotes
        self.hass = hass
        self.area = area
        self.config = config or {}

        # Always store system timezone for reference
        self.system_timezone = dt_util.get_time_zone(hass.config.time_zone) if hass else dt_util.DEFAULT_TIME_ZONE

        # Get area timezone if available
        self.area_timezone = None
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
        # Pass the determined target_timezone to the converter
        self.parser = TimestampParser()
        self.converter = TimezoneConverter(self.target_timezone) # Use target_timezone for converter init
        self.dst_handler = DSTHandler(self.target_timezone) # Use target_timezone for DST handler

        # Determine which timezone to use for hour calculation based on the timezone reference
        # HourCalculator needs the reference mode to decide internally
        self.hour_calculator = HourCalculator(
            timezone=self.target_timezone, # Pass the determined target timezone
            system_timezone=self.system_timezone,
            area_timezone=self.area_timezone,
            timezone_reference=self.timezone_reference
        )

        _LOGGER.debug(f"Initialized timezone service. System TZ: {self.system_timezone}, " +
                    (f"Area TZ: {self.area_timezone}, " if self.area_timezone else "") +
                    f"HA TZ: {self.ha_timezone}, Target TZ: {self.target_timezone}, " +
                    f"Reference Mode: {self.timezone_reference}") # Corrected f-string quotes

    def extract_source_timezone(self, api_data: Dict[str, Any], source_type: str) -> str:
        """Extract timezone from API data or fall back to constants.

        Args:
            api_data: The raw API response data
            source_type: The API source identifier

        Returns:
            Timezone string (e.g., 'Europe/Oslo')
        """ # Corrected docstring quotes
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
        """ # Corrected docstring quotes
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
        """ # Corrected docstring quotes
        _LOGGER.warning("convert_to_ha_timezone is deprecated. Use convert_to_target_timezone.")
        return self.convert_to_target_timezone(dt)

    def convert_to_target_timezone(self, dt):
        """Convert datetime to the effective target timezone (HA or Area).

        Args:
            dt: The datetime to convert

        Returns:
            Converted datetime
        """ # Corrected docstring quotes
        # Ensure dt has a timezone
        if dt.tzinfo is None:
            error_msg = "Cannot convert naive datetime without source timezone"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Use the converter initialized with the target_timezone
        return self.converter.convert(dt, self.target_timezone)


    def normalize_hourly_prices(self, hourly_prices, source_timezone, today_date=None):
        """Convert hourly prices from source timezone to the effective target timezone.""" # Corrected docstring quotes
        # Validate source_timezone
        if not source_timezone or source_timezone == TimezoneConstants.DEFAULT_FALLBACK:
            error_msg = f"Invalid source timezone provided: {source_timezone}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Verify source_timezone can be used
        tz_obj = get_timezone_object(source_timezone)
        if not tz_obj:
            # Try to get timezone from source type
            source_tz_str = get_source_timezone(source_timezone)
            tz_obj = get_timezone_object(source_tz_str)

            if not tz_obj:
                error_msg = f"Cannot find valid timezone object for: {source_timezone}"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)

        # For both timezone reference modes, we convert API data to the determined target timezone
        _LOGGER.debug(f"Converting hourly prices from {source_timezone} to target timezone {self.target_timezone}") # Corrected f-string quotes
        return self.converter.convert_hourly_prices(
            hourly_prices,
            source_timezone,
            self.target_timezone, # Use the target_timezone attribute
            today_date
        )

    def get_current_hour_key(self):
        """Get the current hour key in the appropriate timezone based on the timezone reference setting.""" # Corrected docstring quotes
        # Get current time in different timezones for debugging
        now_utc = datetime.now(timezone.utc)
        now_ha = datetime.now(self.ha_timezone)
        now_area = datetime.now(self.area_timezone) if self.area_timezone else None

        _LOGGER.debug(f"Current time - UTC: {now_utc.strftime('%H:%M:%S')}, HA: {now_ha.strftime('%H:%M:%S')}" +
                     (f", Area ({self.area}): {now_area.strftime('%H:%M:%S')}" if now_area else "")) # Corrected f-string quotes

        hour_key = self.hour_calculator.get_current_hour_key()

        # Log which timezone is being used based on the timezone reference setting
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            used_tz = self.area_timezone
            _LOGGER.debug(f"Using area timezone {used_tz} for hour key (Local Area Time mode)") # Corrected f-string quotes
        else:
            used_tz = self.ha_timezone
            _LOGGER.debug(f"Using HA timezone {used_tz} for hour key (Home Assistant Time mode)") # Corrected f-string quotes

        _LOGGER.debug(f"Current hour key from calculator: {hour_key} (timezone: {used_tz}, area: {self.area})") # Corrected f-string quotes
        return hour_key

    def is_dst_transition_day(self, dt=None):
        """Check if today is a DST transition day.""" # Corrected docstring quotes
        return self.dst_handler.is_dst_transition_day(dt)

    def get_next_hour_key(self) -> str:
        """Get key for the next hour in target timezone.

        Returns:
            String key in format HH:00
        """ # Corrected docstring quotes
        # Delegate to hour calculator for consistent handling
        now = dt_util.now()
        next_hour = now + timedelta(hours=1)

        # Use the hour calculator for consistent timezone handling based on timezone_reference
        return self.hour_calculator.get_hour_key_for_datetime(next_hour)

    def get_today_range(self) -> List[str]:
        """Get list of hour keys for today (represents hours 00-23).""" # Corrected docstring quotes
        # The keys themselves are universal (00:00 to 23:00).
        # The timezone context comes from self.target_timezone when interpreting these keys.
        return [f"{hour:02d}:00" for hour in range(24)] # Corrected f-string quotes

    def get_tomorrow_range(self) -> List[str]:
        """Get list of hour keys for tomorrow (represents hours 00-23).""" # Corrected docstring quotes
        # Same as today but represents tomorrow's hours
        return [f"{hour:02d}:00" for hour in range(24)] # Corrected f-string quotes

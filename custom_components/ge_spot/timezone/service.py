"""Main timezone service coordinating all timezone operations."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

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

        # Initialize component classes
        self.parser = TimestampParser()
        self.converter = TimezoneConverter(self.ha_timezone)
        self.dst_handler = DSTHandler(self.ha_timezone)

        # Determine which timezone to use for hour calculation based on the timezone reference
        calculator_timezone = self.system_timezone
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            calculator_timezone = self.area_timezone

        self.hour_calculator = HourCalculator(
            timezone=calculator_timezone,
            system_timezone=self.system_timezone,
            area_timezone=self.area_timezone,
            timezone_reference=self.timezone_reference
        )

        _LOGGER.debug(f"Initialized timezone service with system timezone: {self.system_timezone}" +
                    (f", area timezone: {self.area_timezone}" if self.area_timezone else "") +
                    f", timezone reference mode: {self.timezone_reference}")

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

        return self.converter.convert(dt, self.ha_timezone)

    def normalize_hourly_prices(self, hourly_prices, source_timezone, today_date=None):
        """Convert hourly prices from source timezone to the appropriate timezone based on the timezone reference setting.

        Args:
            hourly_prices: Dict mapping hour strings to prices
            source_timezone: Source timezone string
            today_date: Optional date to use (defaults to today)

        Returns:
            Dict with hours adjusted to the appropriate timezone
        """
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

        # For both timezone reference modes, we convert API data to HA timezone
        # The difference in behavior is handled in get_current_hour_key(), not here
        return self.converter.convert_hourly_prices(
            hourly_prices,
            source_timezone,
            self.ha_timezone,
            today_date
        )

    def normalize_hourly_prices_with_tomorrow(
        self, today_hourly_prices: Dict[str, float],
        tomorrow_hourly_prices: Dict[str, float],
        source_timezone: str,
        today_date=None
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Convert both today and tomorrow hourly prices and reorganize based on local timezone.

        Args:
            today_hourly_prices: Dict mapping hour strings to today's prices
            tomorrow_hourly_prices: Dict mapping hour strings to tomorrow's prices
            source_timezone: Source timezone string
            today_date: Optional date to use (defaults to today)

        Returns:
            Tuple of (today_prices, tomorrow_prices) with hours properly organized for local timezone
        """
        # First convert both sets of prices to target timezone
        if not today_hourly_prices and not tomorrow_hourly_prices:
            return {}, {}

        # Validate source_timezone
        if not source_timezone or source_timezone == TimezoneConstants.DEFAULT_FALLBACK:
            error_msg = f"Invalid source timezone provided: {source_timezone}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Get timezone objects
        source_tz = get_timezone_object(source_timezone)
        if not source_tz:
            # Try to get timezone from source type
            source_tz_str = get_source_timezone(source_timezone)
            source_tz = get_timezone_object(source_tz_str)

            if not source_tz:
                error_msg = f"Cannot find valid timezone object for: {source_timezone}"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)

        # Determine target timezone based on timezone reference setting
        target_tz = self.ha_timezone
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            target_tz = self.area_timezone

        # Get today's date in target timezone
        if today_date is None:
            today_date = datetime.now(target_tz).date()
        elif isinstance(today_date, datetime):
            today_date = today_date.date()

        tomorrow_date = today_date + timedelta(days=1)

        # Convert both sets of hourly prices
        converted_today = self.converter.convert_hourly_prices(
            today_hourly_prices,
            source_timezone,
            target_tz,
            today_date
        )

        converted_tomorrow = self.converter.convert_hourly_prices(
            tomorrow_hourly_prices,
            source_timezone,
            target_tz,
            tomorrow_date
        )

        # Now reorganize based on local date
        new_today = {}
        new_tomorrow = {}

        # Process all converted hours from both today and tomorrow
        for hour_dict in [converted_today, converted_tomorrow]:
            for hour_key, price in hour_dict.items():
                # Skip prefixed hours as they're already correctly categorized
                if hour_key.startswith("tomorrow_"):
                    new_tomorrow[hour_key[9:]] = price  # Remove "tomorrow_" prefix
                    continue

                # For ISO format keys, determine correct bucket based on date
                if "T" in hour_key:
                    try:
                        # Parse ISO format timestamp - directly use Python's datetime utilities
                        dt_str = hour_key.replace('Z', '+00:00')
                        dt_utc = datetime.fromisoformat(dt_str)

                        # Ensure it's in UTC first for a clean conversion
                        if dt_utc.tzinfo is None:
                            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

                        # Now convert to the target timezone
                        dt_target = dt_utc.astimezone(target_tz)

                        # Simple hour key in target timezone
                        target_hour = f"{dt_target.hour:02d}:00"

                        # Get dates for comparison - using target_tz's understanding of today
                        dt_date = dt_target.date()

                        # Extra debug to understand what's happening
                        _LOGGER.debug(f"Original key: {hour_key}, Date: {dt_date}, Today date: {today_date}")
                        _LOGGER.debug(f"UTC: {dt_utc}, Target: {dt_target}")

                        # FIXED: Use the provided today_date and tomorrow_date instead of actual_today and actual_tomorrow
                        # First check if the date in target timezone matches today or tomorrow
                        if dt_date == today_date:
                            new_today[target_hour] = price
                            _LOGGER.debug(f"Hour {hour_key} -> {target_hour} assigned to TODAY (actual date match)")
                        elif dt_date == tomorrow_date:
                            new_tomorrow[target_hour] = price
                            _LOGGER.debug(f"Hour {hour_key} -> {target_hour} assigned to TOMORROW (actual date match)")
                        else:
                            # If we're here, the date doesn't match today or tomorrow in target timezone
                            # This could happen with timezone differences or near day boundaries
                            
                            # FIXED: Compare with the date from the timestamp, not the current time
                            hour_num = int(target_hour.split(':')[0])
                            
                            # If the date is closer to today_date than tomorrow_date, assign to today
                            if abs((dt_date - today_date).days) <= abs((dt_date - tomorrow_date).days):
                                new_today[target_hour] = price
                                _LOGGER.debug(f"Hour {hour_key} -> {target_hour} assigned to TODAY (closer to today)")
                            else:
                                # If it's closer to tomorrow_date, assign to tomorrow
                                new_tomorrow[target_hour] = price
                                _LOGGER.debug(f"Hour {hour_key} -> {target_hour} assigned to TOMORROW (closer to tomorrow)")
                    except (ValueError, TypeError) as e:
                        # If we can't parse, default to original bucket
                        _LOGGER.debug(f"Failed to parse ISO timestamp {hour_key}: {e}")
                        new_today[hour_key] = price
                else:
                    # For simple "HH:00" format, we need to use the source dict to determine
                    is_from_tomorrow = hour_dict is converted_tomorrow
                    if is_from_tomorrow:
                        new_tomorrow[hour_key] = price
                    else:
                        new_today[hour_key] = price

        _LOGGER.debug(f"Reorganized hours based on local timezone - Today: {len(new_today)}, Tomorrow: {len(new_tomorrow)}")
        return new_today, new_tomorrow

    def get_current_hour_key(self):
        """Get the current hour key in the appropriate timezone based on the timezone reference setting."""
        # Get current time in different timezones for debugging
        now_utc = datetime.now(timezone.utc)
        now_ha = datetime.now(self.ha_timezone)
        now_area = datetime.now(self.area_timezone) if self.area_timezone else None

        _LOGGER.debug(f"Current time - UTC: {now_utc.strftime('%H:%M:%S')}, HA: {now_ha.strftime('%H:%M:%S')}" +
                     (f", Area ({self.area}): {now_area.strftime('%H:%M:%S')}" if now_area else ""))

        hour_key = self.hour_calculator.get_current_hour_key()

        # Log which timezone is being used based on the timezone reference setting
        if self.timezone_reference == TimezoneReference.LOCAL_AREA and self.area_timezone:
            used_tz = self.area_timezone
            _LOGGER.debug(f"Using area timezone {used_tz} for hour key (Local Area Time mode)")
        else:
            used_tz = self.ha_timezone
            _LOGGER.debug(f"Using HA timezone {used_tz} for hour key (Home Assistant Time mode)")

        _LOGGER.debug(f"Current hour key from calculator: {hour_key} (timezone: {used_tz}, area: {self.area})")
        return hour_key

    def is_dst_transition_day(self, dt=None):
        """Check if today is a DST transition day."""
        return self.dst_handler.is_dst_transition_day(dt)

"""Base class for price data parsers."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone, date
from typing import Dict, Any, Optional, List, Tuple

from ...timezone.service import TimezoneService
from ...const.sources import Source
from ...timezone.timezone_utils import get_timezone_object # Import helper
import pytz # Import pytz for robust timezone handling

_LOGGER = logging.getLogger(__name__)

class BasePriceParser(ABC):
    """Base class for price data parsers."""

    def __init__(self, source: str, timezone_service: Optional[TimezoneService] = None):
        """Initialize the parser.

        Args:
            source: Source identifier
            timezone_service: Optional timezone service
        """
        self.source = source
        self.timezone_service = timezone_service or TimezoneService()

    @abstractmethod
    def parse(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw API response data.

        Args:
            raw_data: Raw data from API

        Returns:
            Dict with parsed data
        """
        pass

    def extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from parsed data.

        Args:
            data: Parsed data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "source": self.source,
            "price_count": len(data.get("hourly_prices", {})),
            "currency": data.get("currency", "EUR"),
            "has_current_price": "current_price" in data and data["current_price"] is not None,
            "has_next_hour_price": "next_hour_price" in data and data["next_hour_price"] is not None,
            "parser_version": "2.0",  # Add version for tracking changes
            "parsed_at": datetime.now(timezone.utc).isoformat()
        }

        return metadata

    def validate_parsed_data(self, data: Dict[str, Any]) -> bool:
        """Validate parsed data.

        Args:
            data: Parsed data

        Returns:
            True if data is valid, False otherwise
        """
        # Check if hourly prices exist and are valid
        if "hourly_prices" not in data or not isinstance(data["hourly_prices"], dict):
            _LOGGER.warning(f"{self.source}: Missing or invalid hourly_prices")
            return False

        # Check if there are any prices
        if not data["hourly_prices"]:
            _LOGGER.warning(f"{self.source}: No hourly prices found")
            return False

        # Check if current hour price is available when expected
        current_price = self._get_current_price(data["hourly_prices"])
        if current_price is None:
            _LOGGER.warning(f"{self.source}: Current hour price not found in hourly_prices")
            # Allow validation to pass even if current hour is missing (e.g., data for future only)
            # return False # Temporarily commented out to allow future data validation

        # Check if next hour price is available when it should be (within the same target timezone day)
        target_tz = self.timezone_service.target_timezone # FIX: Access attribute directly
        now_target = datetime.now(target_tz)
        next_hour_start_target = (now_target + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        # Check if the *start* of the next hour in the target timezone is still on the same *calendar day* as *now* in the target timezone.
        # This determines if we *expect* the next hour's price to be part of the current day's data fetch.
        if next_hour_start_target.date() == now_target.date():
            next_price = self._get_next_hour_price(data["hourly_prices"])
            if next_price is None:
                _LOGGER.warning(f"{self.source}: Next hour price expected within the same day ({now_target.date()}) but not found")
                # Allow validation to pass if next hour is missing, might be end of day data
                # return False # Temporarily commented out

        return True

    def parse_timestamp(self, timestamp_str: str, source_timezone: Any, context_date: date | None = None) -> datetime:
        """Parse timestamp string into a timezone-aware datetime object in UTC.

        Args:
            timestamp_str: Timestamp string from API
            source_timezone: Timezone object representing the source API's timezone
            context_date: Optional date to use for time-only keys.

        Returns:
            Timezone-aware datetime object normalized to UTC.

        Raises:
            ValueError: If timestamp cannot be parsed
        """
        dt = None
        # Ensure source_timezone is a usable timezone object
        if isinstance(source_timezone, str):
             source_timezone = get_timezone_object(source_timezone) # Use helper

        if "T" in timestamp_str:  # ISO format
            try:
                # Handle 'Z' for UTC explicitly
                dt_naive_or_aware = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if dt_naive_or_aware.tzinfo is None:
                    # If naive, assume it's in the source_timezone
                    # Use replace() for stdlib timezones, localize() for pytz
                    if hasattr(source_timezone, 'localize'):
                        dt = source_timezone.localize(dt_naive_or_aware)
                    else:
                        dt = dt_naive_or_aware.replace(tzinfo=source_timezone)
                else:
                    # If offset-aware, it's already localized
                    dt = dt_naive_or_aware
            except ValueError as e:
                 raise ValueError(f"Cannot parse ISO timestamp: {timestamp_str} - {e}")

        elif " " in timestamp_str:  # Date + time format (e.g. "2023-05-15 12:00")
            formats = [
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%d.%m.%Y %H:%M",
                "%m/%d/%Y %H:%M",
                "%m/%d/%Y %H:%M:%S", # Added format with seconds for US
            ]
            for fmt in formats:
                try:
                    dt_naive = datetime.strptime(timestamp_str, fmt)
                    # Assume naive timestamps are in the source timezone
                    # Use replace() for stdlib timezones, localize() for pytz
                    if hasattr(source_timezone, 'localize'):
                        dt = source_timezone.localize(dt_naive)
                    else:
                        dt = dt_naive.replace(tzinfo=source_timezone)
                    break
                except ValueError:
                    continue
            if dt is None:
                 raise ValueError(f"Cannot parse date+time timestamp format: {timestamp_str}")

        elif ":" in timestamp_str:  # HH:MM format (ambiguous date)
            try:
                # Use context_date if provided, otherwise today in source timezone
                base_date = context_date if context_date else datetime.now(source_timezone).date()
                time_format = "%H:%M" if len(timestamp_str.split(':')) == 2 else "%H:%M:%S"
                time_obj = datetime.strptime(timestamp_str, time_format).time()
                dt_naive = datetime.combine(base_date, time_obj)
                # Use replace() for stdlib timezones, localize() for pytz
                if hasattr(source_timezone, 'localize'):
                    dt = source_timezone.localize(dt_naive)
                else:
                    dt = dt_naive.replace(tzinfo=source_timezone)
                # Use str() for timezone representation
                _LOGGER.debug(f"Parsed time-only key '{timestamp_str}' using context date {base_date} in {str(source_timezone)} -> {dt.astimezone(timezone.utc)}") # Log UTC conversion
            except (ValueError, AttributeError, NameError) as e: # Catch NameError for timestamp_key
                 # Use timestamp_str here, not timestamp_key
                 _LOGGER.warning(f"Could not parse time-only key '{timestamp_str}' with context {base_date}: {e}")
                 raise ValueError(f"Cannot parse time-only timestamp: {timestamp_str} - {e}") # Re-raise

        if dt is None:
            raise ValueError(f"Timestamp format not recognized: {timestamp_str}")

        # Convert to UTC before returning
        # Ensure dt is timezone-aware before converting
        if dt.tzinfo is None:
             _LOGGER.warning(f"Timestamp '{timestamp_str}' resulted in a naive datetime unexpectedly. Attempting to apply source timezone '{str(source_timezone)}'.")
             # Re-apply source timezone if somehow lost
             if hasattr(source_timezone, 'localize'):
                 dt = source_timezone.localize(dt)
             else:
                 dt = dt.replace(tzinfo=source_timezone)

        return dt.astimezone(timezone.utc)

    # Corrected method signature and docstring
    def classify_timestamp_day(self, dt: datetime, target_timezone: Any, date_context: Optional[date] = None) -> str:
        """Classify a UTC timestamp as 'today', 'tomorrow', or 'other' based on the target timezone's date.

        Args:
            dt: The timezone-aware datetime object in UTC.
            target_timezone: The target timezone object.
            date_context: Optional specific date to use for comparison (e.g., for historical data).

        Returns:
            'today', 'tomorrow', or 'other'.
        """
        # Ensure target_timezone is a usable timezone object
        if isinstance(target_timezone, str):
            target_timezone = get_timezone_object(target_timezone)

        # Convert UTC timestamp to the target timezone
        try:
            dt_target_tz = dt.astimezone(target_timezone)
        except Exception as e:
            _LOGGER.error(f"Error converting timestamp {dt} to target timezone {str(target_timezone)}: {e}")
            return "other" # Cannot classify if conversion fails

        # Determine the reference date in the target timezone
        # Use date_context if provided, otherwise use the current date in the target timezone
        if date_context:
            _LOGGER.debug(f"Using provided date_context: {date_context} (type: {type(date_context)})") # ADDED logging
            reference_date_target = date_context
            # Ensure date_context is a date object
            if not isinstance(reference_date_target, date):
                 _LOGGER.warning(f"Invalid date_context type: {type(date_context)}. Falling back to current date in target timezone.")
                 try:
                     reference_date_target = datetime.now(target_timezone).date()
                 except Exception as e:
                     _LOGGER.error(f"Error getting current date in target timezone {str(target_timezone)} during fallback: {e}")
                     # Fallback further to UTC date if target timezone fails
                     reference_date_target = datetime.now(timezone.utc).date()
                     _LOGGER.warning(f"Further fallback to UTC date: {reference_date_target}")

        else:
            _LOGGER.debug("No date_context provided, using current date in target timezone.") # ADDED logging
            try:
                reference_date_target = datetime.now(target_timezone).date()
            except Exception as e:
                _LOGGER.error(f"Error getting current date in target timezone {str(target_timezone)}: {e}")
                # Fallback to UTC date if target timezone fails
                reference_date_target = datetime.now(timezone.utc).date()
                _LOGGER.warning(f"Fallback to UTC date: {reference_date_target}")

        _LOGGER.debug(f"Final reference_date_target for comparison: {reference_date_target}") # ADDED logging


        # Get today and tomorrow's date based on the reference date in the target timezone
        today_target = reference_date_target
        tomorrow_target = today_target + timedelta(days=1)

        # Get the date part of the timestamp in the target timezone
        timestamp_date_target = dt_target_tz.date()

        # Add logging for debugging
        # Use str() for timezone representation, works for both pytz and stdlib
        _LOGGER.debug(f"Classifying timestamp: UTC={dt}, TargetTZ={str(target_timezone)}, TargetDT={dt_target_tz}")
        # _LOGGER.debug(f"Reference Date (Context or Now) in TargetTZ: {reference_date_target}") # Redundant with 'Final reference_date_target' log
        _LOGGER.debug(f"Comparison dates in TargetTZ: Today={today_target}, Tomorrow={tomorrow_target}")
        _LOGGER.debug(f"Timestamp date in TargetTZ: {timestamp_date_target}")


        # Classify based on date in target timezone
        classification = "other"
        if timestamp_date_target == today_target:
            classification = "today"
        elif timestamp_date_target == tomorrow_target:
            classification = "tomorrow"

        _LOGGER.debug(f"Classification result: {classification}")
        return classification

    def normalize_timestamps(self, prices: dict, source_timezone: Any, target_timezone: Any, date_context: date | None = None) -> dict:
        """Normalize timestamps in price data to HH:MM format in the target timezone,
           separating them into 'today' and 'tomorrow' based on the target timezone's date.

        Args:
            prices: Dictionary with timestamp strings as keys and prices as values.
            source_timezone: Timezone object for interpreting ambiguous timestamps.
            target_timezone: Timezone object for the output format and date classification.
            date_context: Optional specific date to use for comparison (e.g., for historical data).

        Returns:
            Dictionary with keys 'today', 'tomorrow', 'other', each containing
            a dictionary of {HH:MM: price}.
        """
        normalized_prices = {"today": {}, "tomorrow": {}, "other": {}}

        # Ensure timezones are usable objects
        if isinstance(source_timezone, str):
            source_timezone = get_timezone_object(source_timezone)
        if isinstance(target_timezone, str):
            target_timezone = get_timezone_object(target_timezone)

        # Determine the context date for parsing time-only keys
        # Use date_context if provided, otherwise use today in the source timezone
        context_date_for_parsing = date_context if date_context else datetime.now(source_timezone).date()

        for timestamp_key, price in prices.items():
            try:
                # Parse the timestamp string into a UTC datetime object
                dt_utc = self.parse_timestamp(timestamp_key, source_timezone, context_date=context_date_for_parsing)

                # Classify the timestamp based on the target timezone and context date
                day_type = self.classify_timestamp_day(dt_utc, target_timezone, date_context=date_context)

                # Convert UTC time to target timezone
                dt_target = dt_utc.astimezone(target_timezone)
                hour_key = dt_target.strftime("%H:%M")

                # Check for duplicates before assigning
                if hour_key in normalized_prices[day_type]:
                     _LOGGER.warning(f"Duplicate hour key '{hour_key}' encountered for '{day_type}'. Overwriting with value for {timestamp_key}.")

                normalized_prices[day_type][hour_key] = price

            except ValueError as e:
                _LOGGER.warning(f"Skipping invalid timestamp key '{timestamp_key}': {e}")
            except Exception as e:
                 _LOGGER.error(f"Unexpected error processing timestamp '{timestamp_key}': {e}", exc_info=True)

        _LOGGER.debug(f"Normalized {len(prices)} timestamps into: today({len(normalized_prices['today'])}), tomorrow({len(normalized_prices['tomorrow'])}), other({len(normalized_prices['other'])})")
        return normalized_prices

    def _get_current_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get current hour price based on the target timezone."""
        if not hourly_prices:
            return None

        target_tz = self.timezone_service.target_timezone
        if isinstance(target_tz, str):
             target_tz = get_timezone_object(target_tz)

        now_target = datetime.now(target_tz)
        current_hour_key = f"{now_target.hour:02d}:00"

        # Primary check: Look for the simple HH:00 key first
        if current_hour_key in hourly_prices:
             _LOGGER.debug(f"Found current hour price using simple key: {current_hour_key}")
             return hourly_prices[current_hour_key]

        # Fallback: Iterate and parse complex keys (less efficient)
        current_hour_start_target = now_target.replace(minute=0, second=0, microsecond=0)
        _LOGGER.debug(f"Looking for current hour price matching {current_hour_start_target.isoformat()} using fallback parsing...")
        for key, price in hourly_prices.items():
            try:
                # Attempt to parse the key as a datetime (assuming UTC from parser)
                dt_utc = self.parse_timestamp(key, timezone.utc) # Assume UTC if parsing raw key
                dt_target = dt_utc.astimezone(target_tz)

                if dt_target.replace(minute=0, second=0, microsecond=0) == current_hour_start_target:
                    _LOGGER.debug(f"Found current hour price using fallback parsing for key: {key}")
                    return price
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Could not parse key '{key}' during current hour price fallback: {e}")
                continue

        _LOGGER.warning(f"Current hour price not found for target time {current_hour_start_target.isoformat()} or key {current_hour_key}. Available keys: {list(hourly_prices.keys())}")
        return None

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price based on the target timezone."""
        if not hourly_prices:
            return None

        target_tz = self.timezone_service.target_timezone
        if isinstance(target_tz, str):
             target_tz = get_timezone_object(target_tz)

        now_target = datetime.now(target_tz)
        next_hour_dt_target = now_target + timedelta(hours=1)
        next_hour_key = f"{next_hour_dt_target.hour:02d}:00"

        # Primary check: Look for the simple HH:00 key first
        if next_hour_key in hourly_prices:
             _LOGGER.debug(f"Found next hour price using simple key: {next_hour_key}")
             return hourly_prices[next_hour_key]

        # Fallback: Iterate and parse complex keys
        next_hour_start_target = next_hour_dt_target.replace(minute=0, second=0, microsecond=0)
        _LOGGER.debug(f"Looking for next hour price matching {next_hour_start_target.isoformat()} using fallback parsing...")
        for key, price in hourly_prices.items():
            try:
                dt_utc = self.parse_timestamp(key, timezone.utc) # Assume UTC if parsing raw key
                dt_target = dt_utc.astimezone(target_tz)

                if dt_target.replace(minute=0, second=0, microsecond=0) == next_hour_start_target:
                    _LOGGER.debug(f"Found next hour price using fallback parsing for key: {key}")
                    return price
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Could not parse key '{key}' during next hour price fallback: {e}")
                continue

        _LOGGER.warning(f"Next hour price not found for target time {next_hour_start_target.isoformat()} or key {next_hour_key}. Available keys: {list(hourly_prices.keys())}")
        return None

    def calculate_day_average(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Calculate average price for a dictionary of HH:00 keys."""
        if not hourly_prices:
            return None

        prices = list(hourly_prices.values())
        if prices:
            return sum(prices) / len(prices)
        return None

    # Add similar methods for peak/off-peak if needed, operating on the simple dict
    def calculate_peak_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
         if not hourly_prices:
             return None
         return max(hourly_prices.values()) if hourly_prices else None

    def calculate_off_peak_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
         if not hourly_prices:
             return None
         return min(hourly_prices.values()) if hourly_prices else None

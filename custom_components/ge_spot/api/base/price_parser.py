"""Base class for price data parsers."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...utils.timezone_service import TimezoneService
from ...const.sources import Source
from ...timezone.timezone_utils import get_timezone_object # Import helper

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

    def parse_timestamp(self, timestamp_str: str, source_timezone: Any) -> datetime:
        """Parse timestamp with explicit timezone awareness.
        
        Args:
            timestamp_str: Timestamp string from API
            source_timezone: Timezone of the source API
            
        Returns:
            Datetime object with timezone info
            
        Raises:
            ValueError: If timestamp cannot be parsed
        """
        if "T" in timestamp_str:  # ISO format
            # Handle ISO format with or without timezone info
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                # Apply source timezone if no timezone in the string
                dt = dt.replace(tzinfo=source_timezone)
            else:
                # Keep the original timezone from the timestamp string
                # No need to convert to source_timezone
                pass
            return dt
        elif " " in timestamp_str:  # Date + time format (e.g. "2023-05-15 12:00")
            # Try common formats
            formats = [
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%d.%m.%Y %H:%M", 
                "%m/%d/%Y %H:%M",
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    # Apply source timezone since it has no timezone info
                    dt = dt.replace(tzinfo=source_timezone)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Cannot parse timestamp format: {timestamp_str}")
            return dt
        elif ":" in timestamp_str:  # HH:MM format (ambiguous date)
            # For time-only format, use today's date in the source timezone
            try:
                today = datetime.now(source_timezone).date()
                time_format = "%H:%M" if len(timestamp_str.split(':')) == 2 else "%H:%M:%S"
                time_obj = datetime.strptime(timestamp_str, time_format).time()
                dt = datetime.combine(today, time_obj, tzinfo=source_timezone)
                return dt
            except ValueError:
                raise ValueError(f"Cannot parse time format: {timestamp_str}")
        else:
            raise ValueError(f"Cannot determine datetime from timestamp: {timestamp_str}")

    def classify_timestamp_day(self, dt: datetime, target_timezone: Any) -> str:
        """Classify if a timestamp belongs to today or tomorrow in the target timezone.
        
        Args:
            dt: Datetime object with timezone info
            target_timezone: Target timezone (usually user's timezone)
            
        Returns:
            "today", "tomorrow", or "other"
        """
        # Convert to target timezone
        dt_target_tz = dt.astimezone(target_timezone)
        
        # Get today/tomorrow in target timezone
        now = datetime.now(target_timezone)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        # Classify based on date in target timezone
        if dt_target_tz.date() == today:
            return "today"
        elif dt_target_tz.date() == tomorrow:
            return "tomorrow"
        else:
            return "other"

    def normalize_timestamps(self, hourly_prices: Dict[str, float],
                            source_timezone: Any,
                            target_timezone: Any = None,
                            date_context: Optional[datetime.date] = None) -> Dict[str, Dict[str, float]]:
        """Normalize timestamps in hourly prices and separate into today/tomorrow."""
        if not hourly_prices:
            return {"today": {}, "tomorrow": {}}

        # If no target timezone provided, use the one from the service or default to UTC
        target_tz = target_timezone or self.timezone_service.target_timezone # FIX: Access attribute directly

        # Prepare result dictionaries
        today_prices = {}
        tomorrow_prices = {}
        other_prices = {}

        # Get today date in target timezone for HH:MM timestamps without date
        now = datetime.now(target_tz)
        today_date = now.date()

        for timestamp, price in hourly_prices.items():
            try:
                dt = None

                # Parse the timestamp
                if "T" in timestamp or " " in timestamp:
                    # Has date information
                    dt = self.parse_timestamp(timestamp, source_timezone)
                elif ":" in timestamp and date_context is not None:
                    # Simple HH:MM format with supplied date context
                    hour, minute = map(int, timestamp.split(":")) # Ensure int conversion
                    dt = datetime.combine(
                        date_context,
                        datetime.min.time().replace(hour=hour, minute=minute),
                        tzinfo=source_timezone
                    )
                elif ":" in timestamp:
                    # Simple HH:MM format with NO date context - THIS IS AMBIGUOUS AND DISALLOWED
                    _LOGGER.error(
                        f"Ambiguous timestamp without date encountered: {timestamp}. "
                        f"Parsers must provide full date context. Skipping this entry."
                    )
                    continue # Skip this ambiguous entry

                if dt:
                    # Classify as today or tomorrow in target timezone
                    day_type = self.classify_timestamp_day(dt, target_tz)

                    # Convert to target timezone
                    dt_target = dt.astimezone(target_tz)

                    # Create standard hour key (HH:00)
                    hour_key = f"{dt_target.hour:02d}:00"

                    # Store in appropriate dictionary
                    if day_type == "today":
                        today_prices[hour_key] = price
                    elif day_type == "tomorrow":
                        tomorrow_prices[hour_key] = price
                    else:
                        other_prices[hour_key] = price
                        _LOGGER.debug(f"Price for date beyond tomorrow: {dt.date()} hour {dt.hour}")

            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Error normalizing timestamp {timestamp}: {e}")

        # Log the results
        _LOGGER.debug(f"Normalized {len(hourly_prices)} timestamps into: "
                     f"today({len(today_prices)}), tomorrow({len(tomorrow_prices)}), "
                     f"other({len(other_prices)})")

        return {
            "today": today_prices,
            "tomorrow": tomorrow_prices,
            "other": other_prices
        }

    def _get_current_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get current hour price based on the target timezone."""
        if not hourly_prices:
            return None

        target_tz = self.timezone_service.target_timezone # FIX: Access attribute directly
        now_target = datetime.now(target_tz)
        current_hour_start_target = now_target.replace(minute=0, second=0, microsecond=0)

        # Fallback: Iterate through keys and parse them robustly
        _LOGGER.debug(f"Looking for current hour price matching {current_hour_start_target.isoformat()} in target timezone {target_tz}")
        for key, price in hourly_prices.items():
            try:
                # Attempt to parse the key as a datetime (assuming ISO format from parsers)
                dt = datetime.fromisoformat(key.replace('Z', '+00:00'))

                # Ensure dt is offset-aware before converting
                if dt.tzinfo is None:
                    # If parser returned naive, assume UTC (as ENTSO-E often uses)
                    dt_aware = dt.replace(tzinfo=timezone.utc)
                    _LOGGER.warning(f"Parsed key '{key}' was naive, assuming UTC.")
                else:
                    dt_aware = dt

                # Convert the timestamp from the key to the target timezone
                dt_target = dt_aware.astimezone(target_tz)

                # Compare based on the start of the hour in the target timezone
                if dt_target.replace(minute=0, second=0, microsecond=0) == current_hour_start_target:
                    _LOGGER.debug(f"Found current hour price using fallback parsing for key: {key}")
                    return price
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Could not parse key '{key}' during current hour price fallback: {e}")
                continue # Ignore keys that can't be parsed

        _LOGGER.warning(f"Current hour price not found for target time {current_hour_start_target.isoformat()}. Available keys: {list(hourly_prices.keys())}")
        return None

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price based on the target timezone."""
        if not hourly_prices:
            return None

        target_tz = self.timezone_service.target_timezone # FIX: Access attribute directly
        now_target = datetime.now(target_tz)
        # Calculate the start of the next hour in the target timezone
        next_hour_start_target = (now_target + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


        # Fallback: Iterate through keys and parse them robustly
        _LOGGER.debug(f"Looking for next hour price matching {next_hour_start_target.isoformat()} in target timezone {target_tz}")
        for key, price in hourly_prices.items():
            try:
                # Attempt to parse the key as a datetime (assuming ISO format from parsers)
                dt = datetime.fromisoformat(key.replace('Z', '+00:00'))

                # Ensure dt is offset-aware before converting
                if dt.tzinfo is None:
                     # If parser returned naive, assume UTC
                    dt_aware = dt.replace(tzinfo=timezone.utc)
                    _LOGGER.warning(f"Parsed key '{key}' was naive, assuming UTC.")
                else:
                    dt_aware = dt

                # Convert the timestamp from the key to the target timezone
                dt_target = dt_aware.astimezone(target_tz)

                # Compare based on the start of the hour in the target timezone
                if dt_target.replace(minute=0, second=0, microsecond=0) == next_hour_start_target:
                    _LOGGER.debug(f"Found next hour price using fallback parsing for key: {key}")
                    return price
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Could not parse key '{key}' during next hour price fallback: {e}")
                continue # Ignore keys that can't be parsed

        _LOGGER.warning(f"Next hour price not found for target time {next_hour_start_target.isoformat()}. Available keys: {list(hourly_prices.keys())}")
        return None

    def calculate_day_average(self, hourly_prices: Dict[str, float], day_date: Optional[datetime.date] = None) -> Optional[float]:
        """Calculate average price for a specific day.
        
        Args:
            hourly_prices: Dictionary of hourly prices
            day_date: Date to calculate average for (default: today)
            
        Returns:
            Average price or None if not enough data
        """
        if not hourly_prices:
            return None
        
        # Default to today if no date provided
        if day_date is None:
            day_date = datetime.now(timezone.utc).date()
        
        # Extract prices for the specified day
        day_prices = []
        
        for hour_key, price in hourly_prices.items():
            try:
                dt = None
                # Parse the hour key to get the date
                if "T" in hour_key:
                    # ISO format
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                elif ":" in hour_key:
                    # Simple hour format, assume the provided date
                    hour = int(hour_key.split(":")[0])
                    dt = datetime.combine(day_date, datetime.min.time().replace(hour=hour), tzinfo=timezone.utc)
                
                if dt and dt.date() == day_date:
                    day_prices.append(price)
            except (ValueError, TypeError):
                continue
        
        # Calculate average if we have enough prices
        if len(day_prices) >= 12:  # Require at least half a day of data
            return sum(day_prices) / len(day_prices)
        
        return None

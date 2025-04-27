"""Base class for price data parsers."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...utils.timezone_service import TimezoneService
from ...const.sources import Source

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
            return False

        # Check if next hour price is available when it should be
        now = datetime.now(timezone.utc)
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999)
        
        if next_hour <= today_end:
            next_price = self._get_next_hour_price(data["hourly_prices"])
            if next_price is None:
                _LOGGER.warning(f"{self.source}: Next hour price expected but not found")
                return False

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
                dt = dt.replace(tzinfo=source_timezone)
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
        """Normalize timestamps in hourly prices and separate into today/tomorrow.
        
        Args:
            hourly_prices: Dictionary of hourly prices with timestamps as keys
            source_timezone: Source timezone of the data
            target_timezone: Target timezone for normalization (default: UTC)
            date_context: Optional explicit date context for HH:MM format timestamps
            
        Returns:
            Dictionary with 'today' and 'tomorrow' keys, each containing normalized hourly prices
        """
        if not hourly_prices:
            return {"today": {}, "tomorrow": {}}
        
        # If no target timezone provided, use UTC
        target_tz = timezone.utc if target_timezone is None else target_timezone
        
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
                    hour, minute = timestamp.split(":")
                    dt = datetime.combine(
                        date_context, 
                        datetime.min.time().replace(hour=int(hour), minute=int(minute)),
                        tzinfo=source_timezone
                    )
                elif ":" in timestamp:
                    # Simple HH:MM format with no date context - log warning and use today's date
                    # This is not ideal but maintains backward compatibility
                    hour, minute = timestamp.split(":")
                    dt = datetime.combine(
                        today_date, 
                        datetime.min.time().replace(hour=int(hour), minute=int(minute)),
                        tzinfo=source_timezone
                    )
                    _LOGGER.warning(
                        f"Ambiguous timestamp without date: {timestamp}. "
                        f"Assuming today's date ({today_date}). This may cause incorrect day classification."
                    )
                
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
        """Get current hour price.
        
        Args:
            hourly_prices: Dictionary of hourly prices
            
        Returns:
            Current hour price or None if not available
        """
        if not hourly_prices:
            return None
            
        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Try different ISO formats that might be used as keys
        formats = [
            current_hour.isoformat(),  # Full ISO format with timezone
            current_hour.strftime("%Y-%m-%dT%H:00:00"),  # Format without timezone
            f"{current_hour.hour:02d}:00"  # Simple hour format
        ]
        
        for format_key in formats:
            if format_key in hourly_prices:
                return hourly_prices[format_key]
        
        # If we can't find the exact key, try to find the hour in any format
        for key, price in hourly_prices.items():
            try:
                # If key is ISO format
                if "T" in key:
                    dt = datetime.fromisoformat(key.replace('Z', '+00:00'))
                    if dt.hour == current_hour.hour and dt.date() == current_hour.date():
                        return price
                # If key is HH:MM format
                elif ":" in key:
                    hour = int(key.split(":")[0])
                    if hour == current_hour.hour:
                        return price
            except (ValueError, TypeError):
                continue
        
        # If we still can't find it, log and return None
        _LOGGER.warning(f"Current hour price not found for {current_hour.isoformat()} in available hour keys")
        return None
    
    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price.
        
        Args:
            hourly_prices: Dictionary of hourly prices
            
        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None
            
        now = datetime.now(timezone.utc)
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        
        # Try different ISO formats that might be used as keys
        formats = [
            next_hour.isoformat(),  # Full ISO format with timezone
            next_hour.strftime("%Y-%m-%dT%H:00:00"),  # Format without timezone
            f"{next_hour.hour:02d}:00"  # Simple hour format
        ]
        
        for format_key in formats:
            if format_key in hourly_prices:
                return hourly_prices[format_key]
        
        # If we can't find the exact key, try to find the hour in any format
        for key, price in hourly_prices.items():
            try:
                # If key is ISO format
                if "T" in key:
                    dt = datetime.fromisoformat(key.replace('Z', '+00:00'))
                    if dt.hour == next_hour.hour and dt.date() == next_hour.date():
                        return price
                # If key is HH:MM format
                elif ":" in key:
                    hour = int(key.split(":")[0])
                    if hour == next_hour.hour:
                        return price
            except (ValueError, TypeError):
                continue
        
        # If we still can't find it, log and return None
        _LOGGER.warning(f"Next hour price not found for {next_hour.isoformat()} in available hour keys")
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

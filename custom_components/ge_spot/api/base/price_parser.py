"""Base class for API price parsers."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

class BasePriceParser(ABC):
    """Base class for API price parsers."""

    def __init__(self, source: str, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier
            timezone_service: Optional timezone service
        """
        self.source = source
        self.timezone_service = timezone_service
        self.today = datetime.now(timezone.utc).date()
        self.tomorrow = self.today + timedelta(days=1)

    @abstractmethod
    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with today_hourly_prices and tomorrow_hourly_prices
        """
        pass
        
    def parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp string into a datetime object with timezone.
        
        Args:
            timestamp_str: Timestamp string in various possible formats
            
        Returns:
            Timezone-aware datetime object or None if parsing fails
        """
        try:
            # Try ISO format with Z (UTC)
            if 'Z' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return dt
                
            # Try ISO format with timezone
            if '+' in timestamp_str or '-' in timestamp_str and 'T' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str)
                return dt
                
            # Try ISO format without timezone
            if 'T' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
                
            # Try simple HH:00 format
            if ':' in timestamp_str and len(timestamp_str) <= 5:
                hour = int(timestamp_str.split(':')[0])
                if 0 <= hour < 24:
                    # Create today's date with this hour
                    dt = datetime.combine(self.today, datetime.min.time().replace(hour=hour))
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                    
            # Try tomorrow_HH:00 format
            if timestamp_str.startswith("tomorrow_") and ":" in timestamp_str:
                hour_str = timestamp_str[9:]  # Remove "tomorrow_" prefix
                hour = int(hour_str.split(':')[0])
                if 0 <= hour < 24:
                    # Create tomorrow's date with this hour
                    dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour))
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                    
            _LOGGER.debug(f"Could not parse timestamp with standard formats: {timestamp_str}")
            return None
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Error parsing timestamp {timestamp_str}: {e}")
            return None
            
    def format_timestamp_to_iso(self, dt: datetime) -> str:
        """Format a datetime object to ISO 8601 format string.
        
        Args:
            dt: Datetime object
            
        Returns:
            ISO 8601 format string
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:00:00")
        
    def is_tomorrow_timestamp(self, dt: datetime) -> bool:
        """Check if a datetime belongs to tomorrow.
        
        Args:
            dt: Datetime object to check
            
        Returns:
            True if the date matches tomorrow's date
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date() == self.tomorrow

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
            "has_day_average": "day_average_price" in data and data["day_average_price"] is not None
        }

        return metadata

    def validate_parsed_data(self, data: Dict[str, Any]) -> bool:
        """Validate parsed data.

        Args:
            data: Parsed data

        Returns:
            True if data is valid, False otherwise
        """
        # Check if hourly prices exist
        if "hourly_prices" not in data or not isinstance(data["hourly_prices"], dict):
            _LOGGER.warning(f"{self.source}: Missing or invalid hourly_prices")
            return False

        # Check if there are any prices
        if not data["hourly_prices"]:
            _LOGGER.warning(f"{self.source}: No hourly prices found")
            return False

        return True

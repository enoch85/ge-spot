"""Base class for API price parsers."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

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

    @abstractmethod
    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
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

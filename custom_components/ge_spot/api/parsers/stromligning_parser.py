"""Parser for Stromligning API responses."""
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...const.currencies import Currency
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class StromligningParser(BasePriceParser):
    """Parser for Stromligning API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.STROMLIGNING, timezone_service)
        self._price_components = {}

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse Stromligning API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        result = {
            "hourly_prices": {},
            "currency": Currency.DKK
        }

        # Reset price components
        self._price_components = {}

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty Stromligning data received")
            return result

        # Handle pre-processed data
        if isinstance(raw_data, dict):
            # If hourly prices were already processed
            if "hourly_prices" in raw_data and isinstance(raw_data["hourly_prices"], dict):
                result["hourly_prices"] = raw_data["hourly_prices"]
            # Parse prices from Stromligning
            elif "prices" in raw_data and isinstance(raw_data["prices"], list):
                self._parse_price_list(raw_data["prices"], result)
            # Try to parse raw data as JSON
            elif "raw_data" in raw_data and isinstance(raw_data["raw_data"], str):
                try:
                    json_data = json.loads(raw_data["raw_data"])
                    if "prices" in json_data and isinstance(json_data["prices"], list):
                        self._parse_price_list(json_data["prices"], result)
                except json.JSONDecodeError as e:
                    _LOGGER.warning(f"Failed to parse Stromligning raw data as JSON: {e}")
        # Try to parse string as JSON
        elif isinstance(raw_data, str):
            try:
                json_data = json.loads(raw_data)
                if "prices" in json_data and isinstance(json_data["prices"], list):
                    self._parse_price_list(json_data["prices"], result)
            except json.JSONDecodeError as e:
                _LOGGER.warning(f"Failed to parse Stromligning string as JSON: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Stromligning API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.DKK,  # Default currency for Stromligning
            "timezone": "Europe/Copenhagen",
            "area": "DK1",  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Extract price area if available
            if "priceArea" in data:
                metadata["price_area"] = data["priceArea"]
                metadata["area"] = data["priceArea"]
            
            # Check for price components
            component_types = set()
            if "prices" in data and isinstance(data["prices"], list):
                for price_data in data["prices"]:
                    if "price" in price_data and "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                        metadata["has_components"] = True
                        
                        # Extract component types
                        for component in price_data["price"]["components"]:
                            if "name" in component:
                                component_types.add(component["name"])
            
            if component_types:
                metadata["component_types"] = list(component_types)

        return metadata

    def _parse_price_list(self, prices: List[Dict], result: Dict[str, Any]) -> None:
        """Parse price list from Stromligning API response.
        
        Args:
            prices: List of price data
            result: Result dictionary to update
        """
        for price_data in prices:
            if "date" in price_data and "price" in price_data and "value" in price_data["price"]:
                try:
                    # Parse timestamp
                    timestamp_str = price_data["date"]
                    try:
                        # ISO format
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        # Create ISO formatted timestamp
                        hour_key = dt.isoformat()
                        
                        # Parse price
                        price = float(price_data["price"]["value"])
                        
                        # Add to hourly prices
                        result["hourly_prices"][hour_key] = price
                        
                        # Extract price components if available
                        if "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                            self._price_components[hour_key] = {}
                            
                            for component in price_data["price"]["components"]:
                                if "name" in component and "value" in component:
                                    component_name = component["name"]
                                    component_value = float(component["value"])
                                    self._price_components[hour_key][component_name] = component_value
                    except (ValueError, TypeError) as e:
                        _LOGGER.debug(f"Failed to parse Stromligning timestamp: {timestamp_str} - {e}")
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to parse Stromligning price: {e}")

    def get_price_components(self) -> Dict[str, Dict[str, float]]:
        """Get price components extracted during parsing.
        
        Returns:
            Dictionary of price components per hour
        """
        return self._price_components

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Stromligning format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Try ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # Try common Stromligning formats
            formats = [
                "%Y-%m-%dT%H:%M:%S",  # ISO without timezone
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H"  # Date with hour only
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except (ValueError, TypeError):
                    continue

            _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
            return None

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
        current_hour_key = current_hour.isoformat()

        return hourly_prices.get(current_hour_key)

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
        next_hour_key = next_hour.isoformat()

        return hourly_prices.get(next_hour_key)

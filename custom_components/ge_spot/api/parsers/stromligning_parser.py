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
            # Ensure essential keys exist
            if "date" in price_data and "price" in price_data and isinstance(price_data["price"], dict):
                try:
                    # Parse timestamp
                    timestamp_str = price_data["date"]
                    try:
                        # ISO format
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        # Create ISO formatted timestamp key
                        hour_key = dt.isoformat()

                        # --- Refinement: Extract Spotpris component ---
                        spot_price = None
                        components = price_data["price"].get("components")
                        if isinstance(components, list):
                            for component in components:
                                if component.get("name") == "Spotpris" and "value" in component:
                                    try:
                                        spot_price = float(component["value"])
                                        break # Found Spotpris, no need to check further components
                                    except (ValueError, TypeError):
                                        _LOGGER.warning(f"Could not parse Spotpris value: {component.get('value')} for {hour_key}")
                        # --- End Refinement ---

                        # Use Spotpris if found, otherwise log warning (or fallback to total?)
                        if spot_price is not None:
                            result["hourly_prices"][hour_key] = spot_price
                        else:
                            # Log if components exist but Spotpris wasn't found/parsed
                            if components:
                                 _LOGGER.warning(f"Spotpris component not found or invalid in Stromligning data for hour {hour_key}. Components: {components}")
                            # Optionally, fallback to total price if Spotpris is missing?
                            # For consistency, we prefer *not* to fallback to total price here.
                            # If Spotpris is missing, the hour will be missing, handled later.
                            # else:
                            #     # Fallback to total price if needed (less consistent)
                            #     total_price = price_data["price"].get("value")
                            #     if total_price is not None:
                            #         try:
                            #             result["hourly_prices"][hour_key] = float(total_price)
                            #             _LOGGER.debug(f"Using total price as fallback for {hour_key} as Spotpris was missing.")
                            #         except (ValueError, TypeError):
                            #              _LOGGER.warning(f"Could not parse total price fallback value: {total_price} for {hour_key}")


                        # Extract price components if available (for internal storage/debugging)
                        if isinstance(components, list):
                            self._price_components[hour_key] = {}
                            for component in components:
                                if "name" in component and "value" in component:
                                    component_name = component["name"]
                                    try:
                                        component_value = float(component["value"])
                                        self._price_components[hour_key][component_name] = component_value
                                    except (ValueError, TypeError):
                                        _LOGGER.debug(f"Could not parse component '{component_name}' value: {component.get('value')} for {hour_key}")
                    except (ValueError, TypeError) as e:
                        _LOGGER.debug(f"Failed to parse Stromligning timestamp: {timestamp_str} - {e}")
                except Exception as e: # Catch broader errors during item processing
                    _LOGGER.warning(f"Failed to process price item: {price_data}. Error: {e}", exc_info=True)
            else:
                _LOGGER.debug(f"Skipping invalid price item structure: {price_data}")

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

"""Parser for Stromligning API responses."""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from ...const.sources import Source
from ...const.currencies import Currency
from ..base.price_parser import BasePriceParser
from ...const.energy import EnergyUnit  # Add this import

_LOGGER = logging.getLogger(__name__)


class StromligningParser(BasePriceParser):
    """Parser for Stromligning API responses."""

    def __init__(self, source: str = Source.STROMLIGNING, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.STROMLIGNING)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse Stromligning API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with interval prices
        """
        result = {
            "interval_raw": {},
            "currency": Currency.DKK,
            "timezone": "Europe/Copenhagen",
            "source_unit": EnergyUnit.KWH,  # Stromligning provides prices in kWh
        }

        # Reset price components
        self._price_components = {}

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty Stromligning data received")
            return result

        # --- Find the list of prices ---
        prices_list = None
        if isinstance(raw_data, dict):
            # Direct 'prices' key (most common case from API adapter)
            if "prices" in raw_data and isinstance(raw_data["prices"], list):
                prices_list = raw_data["prices"]
                _LOGGER.debug("Using top-level 'prices' list.")
            # Check if raw_data itself contains the list (less likely)
            elif (
                "raw_data" in raw_data
                and isinstance(raw_data["raw_data"], dict)
                and "prices" in raw_data["raw_data"]
                and isinstance(raw_data["raw_data"]["prices"], list)
            ):
                prices_list = raw_data["raw_data"]["prices"]
                _LOGGER.debug("Using 'prices' list nested under 'raw_data'.")
            # Check if raw_data contains a JSON string to decode
            elif "raw_data" in raw_data and isinstance(raw_data["raw_data"], str):
                try:
                    json_data = json.loads(raw_data["raw_data"])
                    if "prices" in json_data and isinstance(json_data["prices"], list):
                        prices_list = json_data["prices"]
                        _LOGGER.debug(
                            "Using 'prices' list decoded from JSON string in 'raw_data'."
                        )
                except json.JSONDecodeError as e:
                    _LOGGER.warning(
                        f"Failed to parse Stromligning raw data string as JSON: {e}"
                    )
        # Check if the input is a JSON string itself
        elif isinstance(raw_data, str):
            try:
                json_data = json.loads(raw_data)
                if "prices" in json_data and isinstance(json_data["prices"], list):
                    prices_list = json_data["prices"]
                    _LOGGER.debug(
                        "Using 'prices' list decoded from direct JSON string input."
                    )
            except json.JSONDecodeError as e:
                _LOGGER.warning(
                    f"Failed to parse Stromligning direct string input as JSON: {e}"
                )

        # --- Validate extracted prices list ---
        if not prices_list:
            _LOGGER.warning(
                "No valid 'prices' list found in Stromligning data after checking various structures."
            )
            _LOGGER.debug(f"Data received by Stromligning parser: {raw_data}")
            return result

        # --- Parse the list ---
        self._parse_price_list(prices_list, result)

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Stromligning API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update(
            {
                "currency": Currency.DKK,  # Default currency for Stromligning
                "timezone": "Europe/Copenhagen",
                "area": "DK1",  # Default area
            }
        )

        # Extract additional metadata
        if isinstance(data, dict):
            # Extract price area if available
            if "priceArea" in data:
                metadata["price_area"] = data["priceArea"]
                metadata["area"] = data["priceArea"]

            # Check for price components and structure
            component_types = set()
            if "prices" in data and isinstance(data["prices"], list) and data["prices"]:
                # Check the first price entry to determine the data structure
                first_price = data["prices"][0]

                # Check if details are available
                if "details" in first_price and isinstance(
                    first_price["details"], dict
                ):
                    metadata["has_details"] = True

                    # Extract component types from details
                    for component_name in first_price["details"].keys():
                        component_types.add(component_name)

                        # Check for nested components (like transmission)
                        component_data = first_price["details"][component_name]
                        if isinstance(component_data, dict):
                            for sub_name in component_data.keys():
                                if sub_name not in ("value", "vat", "total", "unit"):
                                    component_types.add(f"{component_name}.{sub_name}")

            if component_types:
                metadata["component_types"] = list(component_types)

            # Extract additional supplier info if available
            if "supplier" in data:
                metadata["supplier"] = data["supplier"]
            if "company" in data:
                metadata["company"] = data["company"]

        return metadata

    def _parse_price_list(self, prices: List[Dict], result: Dict[str, Any]) -> None:
        """Parse price list from Stromligning API response.

        Args:
            prices: List of price data
            result: Result dictionary to update
        """
        for price_data in prices:
            # Ensure essential keys exist
            if (
                "date" in price_data
                and "price" in price_data
                and isinstance(price_data["price"], dict)
            ):
                try:
                    # Parse timestamp
                    timestamp_str = price_data["date"]
                    try:
                        # ISO format
                        dt = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )
                        # Create ISO formatted timestamp key
                        interval_key = dt.isoformat()
                        price_date = dt.date().isoformat()

                        # --- Price Extraction Logic Change ---
                        # Prioritize the main price.value, similar to the old parser
                        price_value = None
                        if "value" in price_data["price"]:
                            try:
                                price_value = float(price_data["price"]["value"])
                                _LOGGER.debug(
                                    f"Using primary price.value for {interval_key}: {price_value}"
                                )
                            except (ValueError, TypeError):
                                _LOGGER.warning(
                                    f"Could not parse primary price value: {price_data['price'].get('value')} for {interval_key}"
                                )

                        # Fallback to details.electricity.value if primary fails (less likely now)
                        if (
                            price_value is None
                            and "details" in price_data
                            and isinstance(price_data["details"], dict)
                        ):
                            if "electricity" in price_data["details"] and isinstance(
                                price_data["details"]["electricity"], dict
                            ):
                                electricity = price_data["details"]["electricity"]
                                if "value" in electricity:
                                    try:
                                        price_value = float(electricity["value"])
                                        _LOGGER.debug(
                                            f"Using fallback electricity.value as price for {interval_key}: {price_value}"
                                        )
                                    except (ValueError, TypeError):
                                        _LOGGER.warning(
                                            f"Could not parse fallback electricity value: {electricity.get('value')} for {interval_key}"
                                        )
                        # --- End Price Extraction Logic Change ---

                        if price_value is not None:
                            # Store original price value in DKK/kWh
                            result["interval_raw"][
                                interval_key
                            ] = price_value  # Store raw price in DKK/kWh
                            _LOGGER.debug(
                                f"Storing raw price for {interval_key}: {price_value} DKK/kWh"
                            )
                        else:
                            _LOGGER.warning(
                                f"No valid price found in Stromligning data for hour {interval_key}"
                            )

                        # Extract price components from details for internal storage/debugging
                        if "details" in price_data and isinstance(
                            price_data["details"], dict
                        ):
                            self._price_components[interval_key] = {}
                            for component_name, component_data in price_data[
                                "details"
                            ].items():
                                if (
                                    isinstance(component_data, dict)
                                    and "value" in component_data
                                ):
                                    try:
                                        component_value = float(component_data["value"])
                                        self._price_components[interval_key][
                                            component_name
                                        ] = component_value
                                    except (ValueError, TypeError):
                                        _LOGGER.debug(
                                            f"Could not parse component '{component_name}' value: {component_data.get('value')} for {interval_key}"
                                        )

                                # Handle nested components like transmission
                                elif isinstance(component_data, dict):
                                    for sub_name, sub_data in component_data.items():
                                        if (
                                            isinstance(sub_data, dict)
                                            and "value" in sub_data
                                        ):
                                            try:
                                                sub_value = float(sub_data["value"])
                                                self._price_components[interval_key][
                                                    f"{component_name}.{sub_name}"
                                                ] = sub_value
                                            except (ValueError, TypeError):
                                                _LOGGER.debug(
                                                    f"Could not parse nested component '{component_name}.{sub_name}' value: {sub_data.get('value')} for {interval_key}"
                                                )
                    except (ValueError, TypeError) as e:
                        _LOGGER.debug(
                            f"Failed to parse Stromligning timestamp: {timestamp_str} - {e}"
                        )
                except Exception as e:  # Catch broader errors during item processing
                    _LOGGER.warning(
                        f"Failed to process price item: {price_data}. Error: {e}",
                        exc_info=True,
                    )
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
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Try common Stromligning formats
            formats = [
                "%Y-%m-%dT%H:%M:%S",  # ISO without timezone
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H",  # Date with hour only
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except (ValueError, TypeError):
                    continue

            _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
            return None

    def _get_current_price(self, interval_prices: Dict[str, float]) -> Optional[float]:
        """Get current interval price.

        Args:
            interval_prices: Dictionary of interval prices

        Returns:
            Current interval price or None if not available
        """
        if not interval_prices:
            return None

        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_interval_key = current_hour.isoformat()

        return interval_prices.get(current_interval_key)

    def _get_next_interval_price(
        self, interval_prices: Dict[str, float]
    ) -> Optional[float]:
        """Get next interval price.

        Args:
            interval_prices: Dictionary of interval prices

        Returns:
            Next interval price or None if not available
        """
        if not interval_prices:
            return None

        now = datetime.now(timezone.utc)
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        next_interval_key = next_hour.isoformat()

        return interval_prices.get(next_interval_key)

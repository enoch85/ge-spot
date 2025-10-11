"""Parser for ComEd API responses."""
import logging
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...const.currencies import Currency
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser
from ...const.api import ComEd, SourceTimezone
from ..interval_expander import convert_to_target_intervals

_LOGGER = logging.getLogger(__name__)

class ComedParser(BasePriceParser):
    """Parser for ComEd API responses."""

    def __init__(self, source: str = Source.COMED, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.COMED)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse ComEd API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with interval prices
        """
        result = {
            "interval_raw": {},  # Changed from interval_prices
            "currency": Currency.CENTS,  # ComEd API returns prices in cents/kWh, not USD/kWh
            "timezone": SourceTimezone.API_TIMEZONES.get(Source.COMED, "America/Chicago")  # ComEd timezone
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty ComEd data received")
            return result

        # If raw_data is a string (JSON), parse it
        if isinstance(raw_data, str):
            json_data = self._fix_and_parse_json(raw_data)
            if json_data:
                endpoint = ComEd.FIVE_MINUTE_FEED
                self._parse_price_data(json_data, endpoint, result)
        # Handle list of price data directly
        elif isinstance(raw_data, list):
            endpoint = ComEd.FIVE_MINUTE_FEED
            self._parse_price_data(raw_data, endpoint, result)
        # Handle pre-processed data
        elif isinstance(raw_data, dict):
            if "interval_raw" in raw_data and isinstance(raw_data["interval_raw"], dict):  # Changed from interval_prices
                result["interval_raw"] = raw_data["interval_raw"]  # Changed from interval_prices
            elif "raw_data" in raw_data:
                json_data = self._fix_and_parse_json(raw_data["raw_data"])
                if json_data:
                    endpoint = raw_data.get("endpoint", ComEd.FIVE_MINUTE_FEED)
                    self._parse_price_data(json_data, endpoint, result)

        # Calculate current and next interval prices
        if not result.get("current_price"):
            result["current_price"] = self._get_current_price(result["interval_raw"])  # Changed from interval_prices

        if not result.get("next_interval_price"):
            result["next_interval_price"] = self._get_next_interval_price(result["interval_raw"])  # Changed from interval_prices

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from ComEd API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.CENTS,  # ComEd API returns prices in cents/kWh, not USD/kWh
            "timezone": SourceTimezone.API_TIMEZONES.get(Source.COMED, "America/Chicago"),
            "area": "5minutefeed"  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for endpoint information
            if "endpoint" in data:
                metadata["endpoint"] = data["endpoint"]
                metadata["area"] = data["endpoint"]  # Set area to endpoint

        return metadata

    def _fix_and_parse_json(self, raw_data: Any) -> List[Dict]:
        """Fix malformed JSON and parse it.

        Args:
            raw_data: Raw JSON data

        Returns:
            Parsed JSON data as list of dictionaries
        """
        # If already a list or dict, return as is
        if isinstance(raw_data, list):
            return raw_data
        if isinstance(raw_data, dict):
            # If it's a dict with error info from the API client, return empty list
            if "error" in raw_data:
                _LOGGER.error(f"Error in API response: {raw_data.get('message', 'Unknown error')}")
                return []
            # If it's a single item, wrap in a list
            return [raw_data]

        if not isinstance(raw_data, str):
            _LOGGER.warning(f"Unexpected data type: {type(raw_data)}")
            return []

        try:
            # First try standard JSON parsing
            parsed_data = json.loads(raw_data)
            # If parsed data is a dict, wrap it in a list
            if isinstance(parsed_data, dict):
                return [parsed_data]
            return parsed_data
        except json.JSONDecodeError:
            # If that fails, try to fix the malformed JSON
            try:
                # Add missing commas between properties
                fixed_json = re.sub(r'""', '","', raw_data)
                # Fix array brackets if needed
                if not fixed_json.startswith('['):
                    fixed_json = '[' + fixed_json
                if not fixed_json.endswith(']'):
                    fixed_json = fixed_json + ']'
                parsed_data = json.loads(fixed_json)
                # If parsed data is a dict, wrap it in a list
                if isinstance(parsed_data, dict):
                    return [parsed_data]
                return parsed_data
            except (json.JSONDecodeError, ValueError) as e:
                _LOGGER.error(f"Failed to parse ComEd data even after fixing: {e}")
                return []

    def _parse_price_data(self, data: List[Dict], endpoint: str, result: Dict[str, Any]) -> None:
        """Parse ComEd price data into standardized format.

        Args:
            data: Parsed JSON data
            endpoint: API endpoint used
            result: Result dictionary to update
        """
        if not isinstance(data, list) or not data:
            return

        # For 5-minute feed, parse all prices then aggregate to target intervals
        if endpoint == ComEd.FIVE_MINUTE_FEED:
            five_min_prices = {}

            for item in data:
                if "price" in item and "millisUTC" in item:
                    try:
                        # Convert millisUTC to datetime with UTC timezone
                        millis = int(item["millisUTC"])
                        timestamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
                        price = float(item["price"])

                        # Store with ISO timestamp (5-minute granularity)
                        interval_key = timestamp.isoformat()
                        five_min_prices[interval_key] = price

                        # Extract current price from first item if it's the most recent
                        if item == data[0]:
                            result["current_price"] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.debug(f"Skipping invalid data point: {e}")
                        continue

            # Use centralized conversion to convert 5-min data to target intervals
            if five_min_prices:
                converted_prices = convert_to_target_intervals(five_min_prices, source_interval_minutes=5)
                result["interval_raw"].update(converted_prices)

        # For current hour average, just use the current price
        else:
            if "price" in data[0]:
                try:
                    current_price = float(data[0]["price"])
                    result["current_price"] = current_price
                    if "millisUTC" in data[0]:
                        millis = int(data[0]["millisUTC"])
                        timestamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
                    else:
                        timestamp = datetime.now(timezone.utc)
                    hour_dt = timestamp.replace(minute=0, second=0, microsecond=0)
                    interval_key = hour_dt.isoformat()
                    result["interval_raw"][interval_key] = current_price  # Changed from interval_prices
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to parse current hour price: {e}")

    def _get_current_price(self, interval_raw: Dict[str, float]) -> Optional[float]:  # Changed from interval_prices
        """Get current interval price.

        Args:
            interval_raw: Dictionary of interval prices

        Returns:
            Current interval price or None if not available
        """
        if not interval_raw:
            return None

        now = datetime.now(timezone.utc)
        # Round down to nearest 15-minute interval
        minute_rounded = (now.minute // 15) * 15
        current_interval = now.replace(minute=minute_rounded, second=0, microsecond=0)
        current_interval_key = current_interval.isoformat()

        return interval_raw.get(current_interval_key)  # Changed from interval_prices

    def _get_next_interval_price(self, interval_raw: Dict[str, float]) -> Optional[float]:  # Changed from interval_prices
        """Get next interval price.

        Args:
            interval_raw: Dictionary of interval prices

        Returns:
            Next interval price or None if not available
        """
        if not interval_raw:
            return None

        now = datetime.now(timezone.utc)
        # Round down to current 15-minute interval, then add 15 minutes
        minute_rounded = (now.minute // 15) * 15
        current_interval = now.replace(minute=minute_rounded, second=0, microsecond=0)
        next_interval = current_interval + timedelta(minutes=15)
        next_interval_key = next_interval.isoformat()

        return interval_raw.get(next_interval_key)  # Changed from interval_prices

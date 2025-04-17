"""Parser for ComEd API responses."""
import logging
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...const.currencies import Currency
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser
from ...const.api import ComEd, SourceTimezone

_LOGGER = logging.getLogger(__name__)

class ComedParser(BasePriceParser):
    """Parser for ComEd API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.COMED)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse ComEd API response."""
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "hourly_prices": {},
            "currency": Currency.USD,
            "source": self.source
        }

        # Parse the data based on type
        if "raw_data" in data:
            json_data = self._fix_and_parse_json(data["raw_data"])
            if json_data:
                self._parse_price_data(json_data, data.get("endpoint", ComEd.FIVE_MINUTE_FEED), result)

        return result

    def _fix_and_parse_json(self, raw_data: Any) -> List[Dict]:
        """Fix malformed JSON and parse it."""
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
        """Parse ComEd price data."""
        if not isinstance(data, list) or not data:
            return

        # Extract current price from first item
        if "price" in data[0]:
            try:
                current_price = float(data[0]["price"])
                result["current_price"] = current_price

                # Different handling based on endpoint
                if endpoint == ComEd.FIVE_MINUTE_FEED and "millisUTC" in data[0]:
                    timestamp = datetime.fromtimestamp(int(data[0]["millisUTC"]) / 1000, tz=timezone.utc)
                    normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                    hour_key = f"{normalized_hour:02d}:00"
                else:
                    # For current hour average, use the timestamp if available, otherwise use current time
                    if "millisUTC" in data[0]:
                        timestamp = datetime.fromtimestamp(int(data[0]["millisUTC"]) / 1000, tz=timezone.utc)
                        normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                    else:
                        now = datetime.now(timezone.utc)
                        normalized_hour, adjusted_date = normalize_hour_value(now.hour, now.date())
                    hour_key = f"{normalized_hour:02d}:00"

                result["hourly_prices"][hour_key] = current_price
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Failed to parse ComEd price: {e}")

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from ComEd API response."""
        metadata = {
            "currency": Currency.USD,
            "timezone": SourceTimezone.API_TIMEZONES.get(Source.COMED)
        }

        if isinstance(data, dict) and "endpoint" in data:
            metadata["endpoint"] = data["endpoint"]

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from ComEd API response."""
        hourly_prices = {}

        # Get raw data and endpoint
        raw_data = None
        endpoint = ComEd.FIVE_MINUTE_FEED

        if isinstance(data, dict) and "raw_data" in data:
            raw_data = data["raw_data"]
            endpoint = data.get("endpoint", ComEd.FIVE_MINUTE_FEED)
        else:
            raw_data = data

        # Fix and parse JSON data
        json_data = self._fix_and_parse_json(raw_data)
        if not json_data:
            return hourly_prices

        try:
            # For 5-minute feed, we need to group by hour
            if endpoint == ComEd.FIVE_MINUTE_FEED:
                # Use defaultdict to automatically create empty lists for new hour keys
                hour_prices = defaultdict(list)
                hour_timestamps = defaultdict(list)

                for item in json_data:
                    if "price" in item and "millisUTC" in item:
                        try:
                            # Convert millisUTC to datetime with UTC timezone
                            millis = int(item["millisUTC"])
                            timestamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
                            price = float(item["price"])

                            # Group by hour
                            normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                            hour_key = f"{normalized_hour:02d}:00"

                            # Store both price and timestamp for weighted average calculation
                            hour_prices[hour_key].append(price)
                            hour_timestamps[hour_key].append(timestamp)
                        except (ValueError, TypeError) as e:
                            _LOGGER.debug(f"Skipping invalid data point: {e}")
                            continue

                # Calculate average price for each hour
                for hour_key, prices in hour_prices.items():
                    if prices:
                        # Simple average
                        hourly_prices[hour_key] = sum(prices) / len(prices)

            # For current hour average, just use the current price
            else:
                if json_data and "price" in json_data[0]:
                    try:
                        current_price = float(json_data[0]["price"])

                        # Use timestamp if available, otherwise use current time
                        if "millisUTC" in json_data[0]:
                            millis = int(json_data[0]["millisUTC"])
                            timestamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
                        else:
                            timestamp = datetime.now(timezone.utc)

                        normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                        hour_key = f"{normalized_hour:02d}:00"
                        hourly_prices[hour_key] = current_price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse current hour price: {e}")

        except Exception as e:
            _LOGGER.warning(f"Failed to parse ComEd hourly prices: {e}", exc_info=True)

        return hourly_prices

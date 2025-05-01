"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ..base.price_parser import BasePriceParser
from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...const.currencies import Currency

_LOGGER = logging.getLogger(__name__)

class NordpoolPriceParser(BasePriceParser):
    """Parser for Nordpool API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.NORDPOOL, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data dictionary from NordpoolAPI.

        Expects input `data` to be the dictionary returned by NordpoolAPI.fetch_raw_data,
        which includes keys like 'hourly_raw', 'timezone', 'currency', 'raw_data', etc.
        The actual Nordpool JSON response is expected under the 'raw_data' key.
        """
        _LOGGER.debug(f"[NordpoolPriceParser] Input data keys: {list(data.keys())}")

        # The actual Nordpool JSON response is nested under 'raw_data'
        raw_api_response = data.get("raw_data")
        if not raw_api_response or not isinstance(raw_api_response, dict):
            _LOGGER.warning("[NordpoolPriceParser] 'raw_data' key missing or not a dictionary in input.")
            return self._create_empty_result(data) # Return empty structure

        # Extract metadata provided by the API adapter
        source_timezone = data.get("timezone", "UTC") # Default to UTC if missing
        source_currency = data.get("currency", Currency.EUR) # Default to EUR if missing
        area = data.get("area") # Get area if provided by API adapter

        hourly_raw = {}

        # Nordpool data often comes in days (today, tomorrow)
        days_to_process = []
        if isinstance(raw_api_response.get("today"), dict):
            days_to_process.append(raw_api_response["today"])
        if isinstance(raw_api_response.get("tomorrow"), dict):
            days_to_process.append(raw_api_response["tomorrow"])

        # If not today/tomorrow structure, maybe it's the direct list structure?
        if not days_to_process and isinstance(raw_api_response.get("multiAreaEntries"), list):
            days_to_process.append(raw_api_response) # Process the root dict

        if not days_to_process:
            _LOGGER.warning("[NordpoolPriceParser] Could not find 'today'/'tomorrow' dicts or 'multiAreaEntries' list in raw_api_response.")
            return self._create_empty_result(data, source_timezone, source_currency)

        for day_data in days_to_process:
            multi_area_entries = day_data.get("multiAreaEntries")
            if not isinstance(multi_area_entries, list):
                _LOGGER.debug(f"[NordpoolPriceParser] Skipping day_data, 'multiAreaEntries' is not a list: {day_data.keys()}")
                continue

            for entry in multi_area_entries:
                if not isinstance(entry, dict):
                    _LOGGER.debug("[NordpoolPriceParser] Skipping entry, not a dictionary.")
                    continue

                ts_str = entry.get("deliveryStart")
                if not ts_str:
                    _LOGGER.debug("[NordpoolPriceParser] Skipping entry, missing 'deliveryStart'.")
                    continue

                # Ensure area is available
                if not area:
                    _LOGGER.warning("[NordpoolPriceParser] Area not specified, cannot extract price.")
                    continue # Cannot proceed without area

                entry_per_area = entry.get("entryPerArea")
                if not isinstance(entry_per_area, dict) or area not in entry_per_area:
                    _LOGGER.debug(f"[NordpoolPriceParser] Skipping entry for ts {ts_str}, area '{area}' not found in 'entryPerArea'. Keys: {list(entry_per_area.keys()) if isinstance(entry_per_area, dict) else 'N/A'}")
                    continue

                price_str = entry_per_area[area]

                try:
                    # Parse timestamp (assuming UTC from Nordpool)
                    dt_utc = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    hour_key_iso = dt_utc.isoformat() # Use ISO format with UTC offset

                    # Parse price
                    price = float(str(price_str).replace(',', '.')) # Handle comma decimal separator

                    hourly_raw[hour_key_iso] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"[NordpoolPriceParser] Failed to parse timestamp '{ts_str}' or price '{price_str}': {e}")
                    continue

        _LOGGER.debug(f"[NordpoolPriceParser] Parsed {len(hourly_raw)} prices. Keys example: {list(hourly_raw.keys())[:3]}")

        # Construct the final result dictionary expected by DataProcessor
        result = {
            "hourly_raw": hourly_raw,
            "currency": source_currency,
            "timezone": source_timezone, # Pass through the timezone from the API adapter
            "source": Source.NORDPOOL # Add source identifier
        }

        # Validate the result before returning
        if not self.validate(result):
            _LOGGER.warning(f"[NordpoolPriceParser] Validation failed for parsed data. Result: {result}")
            return self._create_empty_result(data, source_timezone, source_currency)

        return result

    def _create_empty_result(self, original_data: Dict[str, Any], timezone: str = "UTC", currency: str = Currency.EUR) -> Dict[str, Any]:
        """Helper to create a standard empty result structure."""
        return {
            "hourly_raw": {},
            "currency": original_data.get("currency", currency),
            "timezone": original_data.get("timezone", timezone),
            "source": Source.NORDPOOL,
        }

    def parse_hourly_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse hourly prices from Nordpool data."""
        _LOGGER.warning("[NordpoolPriceParser] parse_hourly_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area}) # Simulate input
        return parsed_data.get("hourly_raw", {})

    def parse_tomorrow_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse tomorrow's hourly prices from Nordpool data."""
        _LOGGER.warning("[NordpoolPriceParser] parse_tomorrow_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area}) # Simulate input
        return parsed_data.get("hourly_raw", {})

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the parsed data structure."""
        if not isinstance(data, dict): return False
        if "hourly_raw" not in data or not isinstance(data["hourly_raw"], dict):
            _LOGGER.warning(f"[{self.source_id}] Validation failed: Missing or invalid 'hourly_raw'")
            return False
        if "currency" not in data or not data["currency"]:
            _LOGGER.warning(f"[{self.source_id}] Validation failed: Missing or invalid 'currency'")
            return False
        if "timezone" not in data or not data["timezone"]:
            _LOGGER.warning(f"[{self.source_id}] Validation failed: Missing or invalid 'timezone'")
            return False
        if not data["hourly_raw"]:
            _LOGGER.debug(f"[{self.source_id}] Validation warning: 'hourly_raw' is empty.")
        for key, value in data["hourly_raw"].items():
            try:
                datetime.fromisoformat(key.replace('Z', '+00:00'))
            except ValueError:
                _LOGGER.warning(f"[{self.source_id}] Validation failed: Invalid ISO timestamp key '{key}' in 'hourly_raw'")
                return False
            if not isinstance(value, (float, int)):
                _LOGGER.warning(f"[{self.source_id}] Validation failed: Non-numeric price value '{value}' for key '{key}' in 'hourly_raw'")
                return False
        return True

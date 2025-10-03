"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ..base.price_parser import BasePriceParser
from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...const.currencies import Currency
from ...const.energy import EnergyUnit  # Added import

_LOGGER = logging.getLogger(__name__)

class NordpoolPriceParser(BasePriceParser):
    """Parser for Nordpool API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.NORDPOOL, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data dictionary from NordpoolAPI.

        Expects input `data` to be the dictionary returned by NordpoolAPI.fetch_raw_data,
        which includes keys like 'interval_raw', 'timezone', 'currency', 'raw_data', etc.
        The actual Nordpool JSON response is expected under the 'raw_data' key.
        """
        _LOGGER.debug(f"[NordpoolPriceParser] Starting parse. Input data keys: {list(data.keys())}") # Log entry

        # The actual Nordpool JSON response is nested under 'raw_data'
        raw_api_response = data.get("raw_data")
        if not raw_api_response or not isinstance(raw_api_response, dict):
            _LOGGER.warning("[NordpoolPriceParser] 'raw_data' key missing or not a dictionary in input.")
            return self._create_empty_result(data) # Return empty structure
        _LOGGER.debug(f"[NordpoolPriceParser] Found 'raw_data'. Keys: {list(raw_api_response.keys())}") # Log raw_data structure

        # Extract metadata provided by the API adapter
        source_timezone = data.get("timezone", "UTC") # Default to UTC if missing
        source_currency = data.get("currency", Currency.EUR) # Default to EUR if missing
        area = data.get("area") # Get area if provided by API adapter
        _LOGGER.debug(f"[NordpoolPriceParser] Metadata - Area: {area}, Timezone: {source_timezone}, Currency: {source_currency}") # Log metadata

        interval_raw = {}

        # Nordpool data often comes in days (today, tomorrow)
        days_to_process = []
        if isinstance(raw_api_response.get("today"), dict):
            _LOGGER.debug("[NordpoolPriceParser] Found 'today' data.") # Log found today
            days_to_process.append(raw_api_response["today"])
        if isinstance(raw_api_response.get("tomorrow"), dict):
            _LOGGER.debug("[NordpoolPriceParser] Found 'tomorrow' data.") # Log found tomorrow
            days_to_process.append(raw_api_response["tomorrow"])

        # If not today/tomorrow structure, maybe it's the direct list structure?
        if not days_to_process and isinstance(raw_api_response.get("multiAreaEntries"), list):
            _LOGGER.debug("[NordpoolPriceParser] Using root 'multiAreaEntries' list.") # Log direct list usage
            days_to_process.append(raw_api_response) # Process the root dict

        if not days_to_process:
            _LOGGER.warning("[NordpoolPriceParser] Could not find 'today'/'tomorrow' dicts or 'multiAreaEntries' list in raw_api_response.")
            return self._create_empty_result(data, source_timezone, source_currency)
        _LOGGER.debug(f"[NordpoolPriceParser] Processing {len(days_to_process)} day(s) of data.") # Log number of days

        for i, day_data in enumerate(days_to_process):
            _LOGGER.debug(f"[NordpoolPriceParser] Processing day {i+1}. Keys: {list(day_data.keys())}") # Log day processing
            multi_area_entries = day_data.get("multiAreaEntries")
            if not isinstance(multi_area_entries, list):
                _LOGGER.debug(f"[NordpoolPriceParser] Skipping day {i+1}, 'multiAreaEntries' is not a list or missing.")
                continue
            _LOGGER.debug(f"[NordpoolPriceParser] Found {len(multi_area_entries)} entries in 'multiAreaEntries' for day {i+1}.") # Log entry count

            for j, entry in enumerate(multi_area_entries):
                _LOGGER.debug(f"[NordpoolPriceParser] Processing entry {j+1} for day {i+1}.") # Log entry processing
                if not isinstance(entry, dict):
                    _LOGGER.debug(f"[NordpoolPriceParser] Skipping entry {j+1}, not a dictionary.")
                    continue

                ts_str = entry.get("deliveryStart")
                if not ts_str:
                    _LOGGER.debug(f"[NordpoolPriceParser] Skipping entry {j+1}, missing 'deliveryStart'.")
                    continue
                _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Found deliveryStart: {ts_str}") # Log timestamp string

                # Ensure area is available
                if not area:
                    _LOGGER.warning("[NordpoolPriceParser] Area not specified, cannot extract price for this entry.")
                    continue # Cannot proceed without area
                _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Area check passed (Area: {area})") # Log area check

                entry_per_area = entry.get("entryPerArea")
                if not isinstance(entry_per_area, dict):
                     _LOGGER.debug(f"[NordpoolPriceParser] Skipping entry {j+1} for ts {ts_str}, 'entryPerArea' is not a dictionary.")
                     continue
                _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Found entryPerArea: {entry_per_area}") # Log entryPerArea dict

                if area not in entry_per_area:
                    _LOGGER.debug(f"[NordpoolPriceParser] Skipping entry {j+1} for ts {ts_str}, area '{area}' not found in 'entryPerArea'. Available keys: {list(entry_per_area.keys())}")
                    continue
                _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Found area '{area}' in entryPerArea.") # Log area found

                price_str = entry_per_area[area]
                _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Extracted price string: '{price_str}'") # Log price string

                try:
                    # Parse timestamp (assuming UTC from Nordpool)
                    dt_utc = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    interval_key_iso = dt_utc.isoformat() # Use ISO format with UTC offset

                    # Parse price
                    price = float(str(price_str).replace(',', '.')) # Handle comma decimal separator
                    _LOGGER.debug(f"[NordpoolPriceParser] Entry {j+1}: Parsed timestamp: {interval_key_iso}, Parsed price: {price}") # Log parsed values

                    interval_raw[interval_key_iso] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"[NordpoolPriceParser] Entry {j+1}: Failed to parse timestamp '{ts_str}' or price '{price_str}': {e}")
                    continue

        _LOGGER.debug(f"[NordpoolPriceParser] Parsed {len(interval_raw)} prices. Keys example: {list(interval_raw.keys())[:3]}")

        # Construct the final result dictionary expected by DataProcessor
        result = {
            "interval_raw": interval_raw,
            "currency": source_currency,
            "area": area,  # Include the area in the result
            "timezone": source_timezone, # Pass through the timezone from the API adapter
            "source": Source.NORDPOOL, # Add source identifier
            "source_unit": EnergyUnit.MWH # Added source unit
        }

        # Validate the result before returning
        if not self.validate(result):
            _LOGGER.warning(f"[NordpoolPriceParser] Validation failed for parsed data. Result: {result}")
            return self._create_empty_result(data, source_timezone, source_currency)

        return result

    def _create_empty_result(self, original_data: Dict[str, Any], timezone: str = "UTC", currency: str = Currency.EUR) -> Dict[str, Any]:
        """Helper to create a standard empty result structure."""
        return {
            "interval_raw": {},
            "currency": original_data.get("currency", currency),
            "timezone": original_data.get("timezone", timezone),
            "source": Source.NORDPOOL,
            "source_unit": EnergyUnit.MWH  # Added source unit
        }

    def parse_interval_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse interval prices from Nordpool data."""
        _LOGGER.warning("[NordpoolPriceParser] parse_interval_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area})  # Simulate input
        return parsed_data.get("interval_raw", {})

    def parse_tomorrow_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse tomorrow's interval prices from Nordpool data."""
        _LOGGER.warning("[NordpoolPriceParser] parse_tomorrow_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area})  # Simulate input
        return parsed_data.get("interval_raw", {})

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the structure and content of the parsed data."""
        # Add detailed log
        _LOGGER.debug(f"[{self.__class__.__name__}] Starting validation for data: {data}")

        if not isinstance(data, dict):
            _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Data is not a dictionary.")
            return False
        if "interval_raw" not in data or not isinstance(data["interval_raw"], dict):
            _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'interval_raw'")
            return False
        if "currency" not in data or not data["currency"]:
            _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'currency'")
            return False
        if "timezone" not in data or not data["timezone"]:
            _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'timezone'")
            return False
        if "source_unit" not in data or not data["source_unit"]: # Added validation for source_unit
             _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'source_unit'")
             return False
        if not data["interval_raw"]:
            _LOGGER.debug(f"[{self.__class__.__name__}] Validation warning: 'interval_raw' is empty.")
            # Allow empty interval_raw to pass validation, but log it.
            # The check in the test script handles the "no prices found" case.

        for key, value in data["interval_raw"].items():
            try:
                # Test timestamp parsing
                datetime.fromisoformat(key.replace('Z', '+00:00'))
            except ValueError:
                _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Invalid ISO timestamp key '{key}' in 'interval_raw'")
                return False
            if not isinstance(value, (float, int)):
                _LOGGER.warning(f"[{self.__class__.__name__}] Validation failed: Non-numeric price value '{value}' for key '{key}' in 'interval_raw'")
                return False
        _LOGGER.debug(f"[{self.__class__.__name__}] Validation successful.") # Add success log
        return True

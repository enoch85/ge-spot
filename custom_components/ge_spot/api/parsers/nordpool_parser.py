"""Parser for Nordpool API responses."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from ..base.price_parser import BasePriceParser
from ...const.sources import Source
from ...const.currencies import Currency
from ...const.energy import EnergyUnit  # Added import

_LOGGER = logging.getLogger(__name__)


class NordpoolParser(BasePriceParser):
    """Parser for Nordpool API responses."""

    def __init__(self, source: str = Source.NORDPOOL, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.NORDPOOL)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data dictionary from NordpoolAPI.

        Expects input `data` to be the dictionary returned by NordpoolAPI.fetch_raw_data,
        which includes keys like 'interval_raw', 'timezone', 'currency', 'raw_data', etc.
        The actual Nordpool JSON response is expected under the 'raw_data' key.
        """
        _LOGGER.debug(
            f"[NordpoolParser] Starting parse. Input data keys: {list(data.keys())}"
        )

        # The actual Nordpool JSON response is nested under 'raw_data'
        raw_api_response = data.get("raw_data")
        if not raw_api_response or not isinstance(raw_api_response, dict):
            _LOGGER.warning(
                "[NordpoolParser] 'raw_data' key missing or not a dictionary in input."
            )
            return self._create_empty_result(data)

        # Extract metadata provided by the API adapter
        source_timezone = data.get("timezone", "UTC")
        source_currency = data.get("currency", Currency.EUR)
        area = data.get("area")
        _LOGGER.debug(
            f"[NordpoolParser] Metadata - Area: {area}, Timezone: {source_timezone}, Currency: {source_currency}"
        )

        interval_raw = {}

        # Nordpool data often comes in days (today, tomorrow)
        days_to_process = []
        if isinstance(raw_api_response.get("today"), dict):
            days_to_process.append(raw_api_response["today"])
        if isinstance(raw_api_response.get("tomorrow"), dict):
            days_to_process.append(raw_api_response["tomorrow"])

        # If not today/tomorrow structure, maybe it's the direct list structure?
        if not days_to_process and isinstance(
            raw_api_response.get("multiAreaEntries"), list
        ):
            days_to_process.append(raw_api_response)

        if not days_to_process:
            _LOGGER.warning(
                "[NordpoolParser] Could not find 'today'/'tomorrow' dicts or 'multiAreaEntries' list in raw_api_response."
            )
            return self._create_empty_result(data, source_timezone, source_currency)

        _LOGGER.debug(
            f"[NordpoolParser] Processing {len(days_to_process)} day(s) of data"
        )

        for i, day_data in enumerate(days_to_process):
            multi_area_entries = day_data.get("multiAreaEntries")
            if not isinstance(multi_area_entries, list):
                continue

            # Process all entries silently, only log issues
            for entry in multi_area_entries:
                if not isinstance(entry, dict):
                    continue

                ts_str = entry.get("deliveryStart")
                if not ts_str or not area:
                    continue

                entry_per_area = entry.get("entryPerArea")
                if not isinstance(entry_per_area, dict) or area not in entry_per_area:
                    continue

                price_str = entry_per_area[area]

                try:
                    # Parse timestamp (assuming UTC from Nordpool)
                    dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    interval_key_iso = dt_utc.isoformat()

                    # Parse price
                    price = float(str(price_str).replace(",", "."))

                    interval_raw[interval_key_iso] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(
                        f"[NordpoolParser] Failed to parse timestamp '{ts_str}' or price '{price_str}': {e}"
                    )
                    continue

        # Summary log instead of verbose per-entry logging
        _LOGGER.debug(
            f"[NordpoolParser] Parsed {len(interval_raw)} prices. Sample keys: {list(interval_raw.keys())[:3]}"
        )

        # Construct the final result dictionary expected by DataProcessor
        result = {
            "interval_raw": interval_raw,
            "currency": source_currency,
            "area": area,
            "timezone": source_timezone,
            "source": Source.NORDPOOL,
            "source_unit": EnergyUnit.MWH,
        }

        # Validate the result before returning
        if not self.validate(result):
            _LOGGER.warning(
                f"[NordpoolParser] Validation failed for parsed data. Result: {result}"
            )
            return self._create_empty_result(data, source_timezone, source_currency)

        return result

    def _create_empty_result(
        self,
        original_data: Dict[str, Any],
        timezone: str = "UTC",
        currency: str = Currency.EUR,
    ) -> Dict[str, Any]:
        """Helper to create a standard empty result structure."""
        return {
            "interval_raw": {},
            "currency": original_data.get("currency", currency),
            "timezone": original_data.get("timezone", timezone),
            "source": Source.NORDPOOL,
            "source_unit": EnergyUnit.MWH,  # Added source unit
        }

    def parse_interval_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse interval prices from Nordpool data."""
        _LOGGER.warning("[NordpoolParser] parse_interval_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area})  # Simulate input
        return parsed_data.get("interval_raw", {})

    def parse_tomorrow_prices(
        self, data: Dict[str, Any], area: str
    ) -> Dict[str, float]:
        """Parse tomorrow's interval prices from Nordpool data."""
        _LOGGER.warning("[NordpoolParser] parse_tomorrow_prices might be outdated.")
        parsed_data = self.parse({"raw_data": data, "area": area})  # Simulate input
        return parsed_data.get("interval_raw", {})

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the structure and content of the parsed data."""
        # Add detailed log
        _LOGGER.debug(
            f"[{self.__class__.__name__}] Starting validation for data: {data}"
        )

        if not isinstance(data, dict):
            _LOGGER.warning(
                f"[{self.__class__.__name__}] Validation failed: Data is not a dictionary."
            )
            return False
        if "interval_raw" not in data or not isinstance(data["interval_raw"], dict):
            _LOGGER.warning(
                f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'interval_raw'"
            )
            return False
        if "currency" not in data or not data["currency"]:
            _LOGGER.warning(
                f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'currency'"
            )
            return False
        if "timezone" not in data or not data["timezone"]:
            _LOGGER.warning(
                f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'timezone'"
            )
            return False
        if (
            "source_unit" not in data or not data["source_unit"]
        ):  # Added validation for source_unit
            _LOGGER.warning(
                f"[{self.__class__.__name__}] Validation failed: Missing or invalid 'source_unit'"
            )
            return False
        if not data["interval_raw"]:
            _LOGGER.debug(
                f"[{self.__class__.__name__}] Validation warning: 'interval_raw' is empty."
            )
            # Allow empty interval_raw to pass validation, but log it.
            # The check in the test script handles the "no prices found" case.

        for key, value in data["interval_raw"].items():
            try:
                # Test timestamp parsing
                datetime.fromisoformat(key.replace("Z", "+00:00"))
            except ValueError:
                _LOGGER.warning(
                    f"[{self.__class__.__name__}] Validation failed: Invalid ISO timestamp key '{key}' in 'interval_raw'"
                )
                return False
            if not isinstance(value, (float, int)):
                _LOGGER.warning(
                    f"[{self.__class__.__name__}] Validation failed: Non-numeric price value '{value}' for key '{key}' in 'interval_raw'"
                )
                return False
        _LOGGER.debug(
            f"[{self.__class__.__name__}] Validation successful."
        )  # Add success log
        return True

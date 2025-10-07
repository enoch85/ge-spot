"""Parser for Energy-Charts API responses."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from ..base.price_parser import BasePriceParser
from ...const.sources import Source
from ...const.currencies import Currency
from ...const.energy import EnergyUnit

_LOGGER = logging.getLogger(__name__)

class EnergyChartsParser(BasePriceParser):
    """Parser for Energy-Charts API responses.
    
    Energy-Charts API returns data with:
    - unix_seconds: Array of unix timestamps (seconds since epoch)
    - price: Array of prices in EUR/MWh
    - unit: "EUR / MWh"
    - license_info: Attribution information
    
    This parser converts unix timestamps to ISO format and builds
    the interval_raw dictionary required by the data processor.
    """

    def __init__(self, timezone_service=None):
        """Initialize the parser.
        
        Args:
            timezone_service: Optional timezone service
        """
        super().__init__(Source.ENERGY_CHARTS, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data dictionary from EnergyChartsAPI.

        Expects input `data` to be the dictionary returned by EnergyChartsAPI.fetch_raw_data,
        which includes keys like 'raw_data', 'timezone', 'currency', 'area', etc.
        The actual Energy-Charts JSON response is under the 'raw_data' key.

        Args:
            data: Dictionary containing raw API response and metadata

        Returns:
            Dictionary with parsed interval data:
            {
                "interval_raw": {iso_timestamp: price, ...},
                "currency": "EUR",
                "area": "DE-LU",
                "timezone": "Europe/Berlin",
                "source": "energy_charts",
                "source_unit": "MWh",
                "license_info": "..."
            }
        """
        _LOGGER.debug(f"[EnergyChartsParser] Starting parse. Input data keys: {list(data.keys())}")

        # Extract the actual API response
        raw_api_response = data.get("raw_data")
        if not raw_api_response or not isinstance(raw_api_response, dict):
            _LOGGER.warning("[EnergyChartsParser] 'raw_data' key missing or not a dictionary")
            return self._create_empty_result(data)

        # Extract metadata
        source_timezone = data.get("timezone", "Europe/Berlin")
        source_currency = data.get("currency", Currency.EUR)
        area = data.get("area")
        license_info = data.get("license_info", "")

        _LOGGER.debug(
            f"[EnergyChartsParser] Metadata - Area: {area}, "
            f"Timezone: {source_timezone}, Currency: {source_currency}"
        )

        # Extract unix timestamps and prices
        unix_seconds = raw_api_response.get("unix_seconds", [])
        prices = raw_api_response.get("price", [])

        if not unix_seconds or not prices:
            _LOGGER.warning("[EnergyChartsParser] No timestamps or prices in response")
            return self._create_empty_result(data, source_timezone, source_currency)

        if len(unix_seconds) != len(prices):
            _LOGGER.error(
                f"[EnergyChartsParser] Mismatch: {len(unix_seconds)} timestamps "
                f"vs {len(prices)} prices"
            )
            return self._create_empty_result(data, source_timezone, source_currency)

        _LOGGER.debug(f"[EnergyChartsParser] Processing {len(unix_seconds)} data points")

        # Build interval_raw dictionary
        interval_raw = {}
        for timestamp, price in zip(unix_seconds, prices):
            try:
                # Convert unix timestamp to datetime UTC
                dt_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                interval_key_iso = dt_utc.isoformat()
                
                # Store price (already in EUR/MWh)
                interval_raw[interval_key_iso] = float(price)
                
            except (ValueError, TypeError) as e:
                _LOGGER.error(
                    f"[EnergyChartsParser] Failed to parse timestamp {timestamp} "
                    f"or price {price}: {e}"
                )
                continue

        _LOGGER.debug(
            f"[EnergyChartsParser] Parsed {len(interval_raw)} prices. "
            f"Sample keys: {list(interval_raw.keys())[:3]}"
        )

        # Construct result
        result = {
            "interval_raw": interval_raw,
            "currency": source_currency,
            "area": area,
            "timezone": source_timezone,
            "source": Source.ENERGY_CHARTS,
            "source_unit": EnergyUnit.MWH,
            "license_info": license_info
        }

        if not self.validate(result):
            _LOGGER.warning(f"[EnergyChartsParser] Validation failed for parsed data")
            return self._create_empty_result(data, source_timezone, source_currency)

        return result

    def _create_empty_result(
        self, 
        original_data: Dict[str, Any], 
        timezone: str = "Europe/Berlin", 
        currency: str = Currency.EUR
    ) -> Dict[str, Any]:
        """Helper to create a standard empty result structure.
        
        Args:
            original_data: Original data dictionary
            timezone: Timezone string (default: Europe/Berlin)
            currency: Currency string (default: EUR)
            
        Returns:
            Empty result dictionary with proper structure
        """
        return {
            "interval_raw": {},
            "currency": original_data.get("currency", currency),
            "timezone": original_data.get("timezone", timezone),
            "source": Source.ENERGY_CHARTS,
            "source_unit": EnergyUnit.MWH
        }

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the structure and content of the parsed data.

        Args:
            data: Parsed data dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        _LOGGER.debug(f"[{self.__class__.__name__}] Starting validation")

        if not isinstance(data, dict):
            _LOGGER.warning(f"[{self.__class__.__name__}] Data is not a dictionary")
            return False
        
        required_fields = ["interval_raw", "currency", "timezone", "source_unit"]
        for field in required_fields:
            if field not in data or not data[field]:
                _LOGGER.warning(f"[{self.__class__.__name__}] Missing or invalid '{field}'")
                return False

        # Validate interval_raw structure
        interval_raw = data.get("interval_raw", {})
        if not isinstance(interval_raw, dict):
            _LOGGER.warning(f"[{self.__class__.__name__}] 'interval_raw' is not a dictionary")
            return False

        # Validate timestamps and prices
        for key, value in interval_raw.items():
            try:
                # Validate ISO timestamp format
                datetime.fromisoformat(key.replace('Z', '+00:00'))
            except ValueError:
                _LOGGER.warning(f"[{self.__class__.__name__}] Invalid timestamp key '{key}'")
                return False
            
            # Validate price is numeric
            if not isinstance(value, (float, int)):
                _LOGGER.warning(f"[{self.__class__.__name__}] Non-numeric price '{value}'")
                return False

        _LOGGER.debug(f"[{self.__class__.__name__}] Validation successful")
        return True

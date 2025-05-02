"""Data processor for electricity spot prices."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price import ElectricityPriceAdapter
from ..utils.exchange_service import get_exchange_service, ExchangeRateService
from ..timezone.source_tz import get_source_timezone
from ..const.config import Config
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..timezone.service import TimezoneService
from ..api.base.data_structure import PriceStatistics, StandardizedPriceData
from ..const.currencies import Currency
# Import Defaults class to access PRECISION
from ..const.defaults import Defaults
from ..const.energy import EnergyUnit
# Fix import path for CacheManager
from .cache_manager import CacheManager

from ..timezone.timezone_converter import TimezoneConverter # Import TimezoneConverter
from ..price.currency_converter import CurrencyConverter # Import CurrencyConverter
from ..price.statistics import calculate_statistics
# Use relative import for timezone_utils
from ..timezone.timezone_utils import get_timezone_object
# Use absolute component path for sources
from custom_components.ge_spot.const.sources import Source
from ..const.attributes import Attributes
# Import BasePriceParser for type hinting
from ..api.base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

# NOTE: All API modules should return raw, unprocessed data in this standardized format:
# {
#     "hourly_prices": {"HH:00" or ISO: price, ...},
#     "currency": str,
#     "timezone": str,
#     "area": str,
#     "raw_data": dict (original API response),
#     "source": str,
#     "last_updated": ISO8601 str,
#     ...
# }
# All timezone, currency, and statistics logic must be handled here or in the adapter, not in the API modules.
# TODO: Refactor all remaining API modules to follow this pattern for consistency and maintainability.

class DataProcessor:
    """Processor for formatting and enriching price data AFTER source selection."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        target_currency: str,
        config: Dict[str, Any],
        tz_service: TimezoneService,
        # Accept the manager initially, get exchange_service later
        manager: Any
    ):
        """Initialize the data processor.

        Args:
            hass: Home Assistant instance
            area: Area code
            target_currency: Target currency code
            config: Configuration dictionary
            tz_service: Timezone service instance
            manager: Manager instance to retrieve services
        """
        self.hass = hass
        self.area = area
        self.target_currency = target_currency
        self.config = config
        self._tz_service = tz_service
        # Store manager to get exchange_service later
        self._manager = manager
        self._exchange_service: Optional[ExchangeRateService] = None

        # Extract config settings needed for processing
        self.vat_rate = config.get(Config.VAT, Defaults.VAT_RATE) / 100  # Convert % to rate
        self.include_vat = config.get(Config.INCLUDE_VAT, Defaults.INCLUDE_VAT)
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
        # Use Defaults.PRECISION instead of DEFAULT_PRICE_PRECISION
        self.precision = config.get(Config.PRECISION, Defaults.PRECISION)

        # Instantiate converters
        self._tz_converter = TimezoneConverter(tz_service)
        # CurrencyConverter needs exchange service, which is async, handle in process
        self._currency_converter: Optional[CurrencyConverter] = None


    async def _ensure_exchange_service(self):
        """Ensure the exchange service is available from the manager."""
        if self._exchange_service is None:
            # Check if the _manager is already an ExchangeRateService (for tests)
            if hasattr(self._manager, 'get_rates'):
                self._exchange_service = self._manager
                await self._exchange_service.get_rates()  # Initialize the rates
            # Manager with _exchange_service attribute (normal operation)
            elif hasattr(self._manager, '_exchange_service') and self._manager._exchange_service is not None:
                self._exchange_service = self._manager._exchange_service
            # Manager with _ensure_exchange_service method (normal operation)
            elif hasattr(self._manager, '_ensure_exchange_service'):
                await self._manager._ensure_exchange_service()
                self._exchange_service = self._manager._exchange_service
            else:
                _LOGGER.error("Exchange service not available in DataProcessor")
                raise RuntimeError("Exchange service could not be initialized or retrieved.")
        
        # Instantiate CurrencyConverter once exchange service is ready
        if self._currency_converter is None and self._exchange_service is not None:
            self._currency_converter = CurrencyConverter(
                exchange_service=self._exchange_service,
                target_currency=self.target_currency,
                display_unit=self.display_unit,
                include_vat=self.include_vat,
                vat_rate=self.vat_rate
            )
        
        # Ensure we have a valid currency converter
        if self._currency_converter is None:
            _LOGGER.error("Failed to initialize currency converter")
            raise RuntimeError("Currency converter could not be initialized.")


    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Accepts raw data from API adapter (e.g., entsoe.py)
        # Expects keys: 'hourly_raw', 'timezone', 'currency', 'source_name', ...
        await self._ensure_exchange_service()

        # --- Step 0: Identify Source and Get Parser ---
        source_name = data.get("data_source") or data.get("source") # Get source name
        if not source_name:
            _LOGGER.error(f"Missing 'data_source' or 'source' key in input data for area {self.area}. Cannot determine parser.")
            return self._generate_empty_processed_result(data, error="Missing source identifier")

        parser = self._get_parser(source_name)
        if not parser:
            _LOGGER.error(f"No parser found for source '{source_name}' in area {self.area}.")
            return self._generate_empty_processed_result(data, error=f"No parser for source {source_name}")

        # --- Step 1: Parse Raw Data ---
        try:
            # Pass the entire raw dictionary from FallbackManager to the parser
            parsed_data = parser.parse(data)
            _LOGGER.debug(f"[{self.area}] Parser {parser.__class__.__name__} output keys: {list(parsed_data.keys())}")
        except Exception as parse_err:
            _LOGGER.error(f"[{self.area}] Error parsing data from source '{source_name}': {parse_err}", exc_info=True)
            return self._generate_empty_processed_result(data, error=f"Parsing error: {parse_err}")

        # Validate parser output
        if not parsed_data or not isinstance(parsed_data, dict) or not parsed_data.get("hourly_raw"):
            _LOGGER.warning(f"[{self.area}] Parser for source '{source_name}' returned invalid or empty data. Parsed keys: {list(parsed_data.keys()) if isinstance(parsed_data, dict) else 'N/A'}")
            # Include the structure passed to the parser in the warning for better debugging
            _LOGGER.debug(f"[{self.area}] Data passed to parser {parser.__class__.__name__}: {data}") # Log the data passed
            return self._generate_empty_processed_result(data, error=f"Parser {source_name} returned invalid data")

        raw_hourly_prices = parsed_data["hourly_raw"]
        source_timezone = parsed_data.get("timezone")
        source_currency = parsed_data.get("currency")
        # Keep original raw API data if available in the input `data`
        raw_api_data = data.get("raw_data") or data.get("xml_responses") or data.get("dict_response")

        if not source_timezone:
            _LOGGER.error(f"Missing 'timezone' key in parsed data for source {source_name}. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing timezone key after parsing")
        if not source_currency:
            _LOGGER.error(f"Missing currency for source {source_name} after parsing. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing currency after parsing")

        # --- Step 2: Normalize Timezones ---
        try:
            # This will convert ISO timestamp keys to 'YYYY-MM-DD HH:00' format in target timezone
            normalized_prices = self._tz_converter.normalize_hourly_prices(
                raw_hourly_prices,
                source_timezone,
                preserve_date=True  # Keep date part for today/tomorrow split
            )

            # Split into today/tomorrow using the normalized keys with dates
            normalized_today, normalized_tomorrow = self._tz_converter.split_into_today_tomorrow(normalized_prices)
            
            # Log the results of normalization and splitting
            _LOGGER.debug(f"Normalized {len(raw_hourly_prices)} timestamps into: today({len(normalized_today)}), tomorrow({len(normalized_tomorrow)})")
        except Exception as e:
            _LOGGER.error(f"Error during timestamp normalization for {self.area}: {e}", exc_info=True)
            return self._generate_empty_processed_result(data, error=f"Timestamp normalization error: {e}")

        # --- Step 3: Currency/Unit Conversion ---
        ecb_rate = None
        ecb_updated = None
        final_today_prices = {}
        # Get source unit from the input data, default to MWh if not present
        source_unit = data.get("source_unit", EnergyUnit.MWH)
        _LOGGER.debug(f"[{self.area}] Using source unit '{source_unit}' for currency conversion.")

        if normalized_today:
            converted_today, rate, rate_ts = await self._currency_converter.convert_hourly_prices(
                hourly_prices=normalized_today,
                source_currency=source_currency,
                # Pass the determined source_unit
                source_unit=source_unit
            )
            final_today_prices = converted_today
            if rate is not None:
                ecb_rate = rate
                ecb_updated = rate_ts
        final_tomorrow_prices = {}
        if normalized_tomorrow:
            converted_tomorrow, rate, rate_ts = await self._currency_converter.convert_hourly_prices(
                hourly_prices=normalized_tomorrow,
                source_currency=source_currency,
                # Pass the determined source_unit
                source_unit=source_unit
            )
            final_tomorrow_prices = converted_tomorrow
            if ecb_rate is None and rate is not None:
                ecb_rate = rate
                ecb_updated = rate_ts

        # --- Step 4: Build Result ---
        processed_result = {
            "source": source_name, # Use source_name identified earlier
            "area": self.area,
            "source_currency": source_currency,
            "target_currency": self.target_currency,
            "source_timezone": source_timezone,
            "target_timezone": str(self._tz_service.target_timezone) if self._tz_service else None,
            "hourly_prices": final_today_prices,
            "tomorrow_hourly_prices": final_tomorrow_prices,
            "raw_hourly_prices_original": raw_hourly_prices, # Store the output from the parser
            "current_price": None,
            "next_hour_price": None,
            "current_hour_key": None,
            "next_hour_key": None,
            "statistics": PriceStatistics(complete_data=False).to_dict(),
            "tomorrow_statistics": PriceStatistics(complete_data=False).to_dict(),
            "vat_rate": self.vat_rate * 100 if self.include_vat else 0,
            "vat_included": self.include_vat,
            "display_unit": self.display_unit,
            "raw_data": raw_api_data, # Store original raw API data
            "ecb_rate": ecb_rate,
            "ecb_updated": ecb_updated,
            "has_tomorrow_prices": bool(final_tomorrow_prices),
            "attempted_sources": data.get("attempted_sources", []),
            "fallback_sources": data.get("fallback_sources", []),
            "using_cached_data": data.get("using_cached_data", False),
            "fetched_at": data.get("fetched_at")
        }

        # --- Add Stromligning Attribution ---
        if source_name == Source.STROMLIGNING:
            processed_result[Attributes.DATA_SOURCE_ATTRIBUTION] = "Data provided by Strømligning. https://stromligning.dk"
        # --- End Attribution ---

        # Initialize tomorrow_valid flag
        processed_result["tomorrow_valid"] = False

        # --- Step 5: Calculate Statistics and Current/Next Prices ---
        try:
            # Calculate Today's Statistics and Current/Next Prices
            if final_today_prices:
                current_hour_key = self._tz_service.get_current_hour_key()
                next_hour_key = self._tz_service.get_next_hour_key()
                processed_result["current_hour_key"] = current_hour_key
                processed_result["next_hour_key"] = next_hour_key
                processed_result["current_price"] = final_today_prices.get(current_hour_key)
                processed_result["next_hour_price"] = final_today_prices.get(next_hour_key)

                today_keys = set(self._tz_service.get_today_range())
                found_keys = set(final_today_prices.keys())
                # Allow statistics if at least 20 hours are present
                today_complete_enough = len(found_keys) >= 20 

                if today_complete_enough:
                    stats = self._calculate_statistics(final_today_prices)
                    # Mark as complete only if all 24 hours are present
                    stats.complete_data = today_keys.issubset(found_keys) 
                    processed_result["statistics"] = stats.to_dict()
                    _LOGGER.debug(f"Calculated today's statistics for {self.area}: {processed_result['statistics']}") # Log today's stats
                else:
                    missing_keys = sorted(list(today_keys - found_keys))
                    # Update warning message threshold
                    _LOGGER.warning(f"Insufficient data for today ({len(found_keys)}/{len(today_keys)} keys found, need 20), skipping statistics calculation for {self.area}. Missing: {missing_keys}")
                    processed_result["statistics"] = PriceStatistics(complete_data=False).to_dict()
            else:
                _LOGGER.warning(f"No final prices for today available after processing for area {self.area}, skipping stats.")
                processed_result["statistics"] = PriceStatistics(complete_data=False).to_dict()

            # Calculate Tomorrow's Statistics
            if final_tomorrow_prices:
                tomorrow_keys = set(self._tz_service.get_tomorrow_range())
                found_keys = set(final_tomorrow_prices.keys())
                # Allow statistics if at least 20 hours are present
                tomorrow_complete_enough = len(found_keys) >= 20

                if tomorrow_complete_enough:
                    stats = self._calculate_statistics(final_tomorrow_prices)
                     # Mark as complete only if all 24 hours are present
                    stats.complete_data = tomorrow_keys.issubset(found_keys)
                    processed_result["tomorrow_statistics"] = stats.to_dict()
                    # Set tomorrow_valid if we have enough data for stats, even if not fully complete
                    processed_result["tomorrow_valid"] = True 
                    _LOGGER.debug(f"Calculated tomorrow's statistics for {self.area}: {processed_result['tomorrow_statistics']}") # Log tomorrow's stats
                else:
                    missing_keys = sorted(list(tomorrow_keys - found_keys))
                    # Update warning message threshold
                    _LOGGER.warning(f"Insufficient data for tomorrow ({len(found_keys)}/{len(tomorrow_keys)} keys found, need 20), skipping statistics calculation for {self.area}. Missing: {missing_keys}")
                    processed_result["tomorrow_statistics"] = PriceStatistics(complete_data=False).to_dict()
            else:
                # No tomorrow prices, ensure stats reflect incompleteness
                processed_result["tomorrow_statistics"] = PriceStatistics(complete_data=False).to_dict()

        except Exception as e:
            _LOGGER.error(f"Error during data processing for area {self.area}: {e}", exc_info=True)
            # Ensure exchange service is ready even on error path
            try:
                await self._ensure_exchange_service()
            except Exception as init_err:
                 _LOGGER.error(f"Failed to ensure exchange service during error handling: {init_err}")
            # Return structure with error, preserving original raw data if possible
            error_result = self._generate_empty_processed_result(data, error=str(e))
            error_result["raw_hourly_prices_original"] = raw_hourly_prices # Keep original raw input
            return error_result

        # Ensure source_timezone is always set in processed_result
        if not processed_result.get("source_timezone"):
             _LOGGER.error(f"Source timezone ('source_timezone') is missing in the processed result for area {self.area} after processing. This indicates an issue.")
             processed_result["error"] = processed_result.get("error", "") + " Missing source timezone after processing."

        _LOGGER.info(f"Successfully processed data for area {self.area}. Source: {source_name}, Today Prices: {len(processed_result['hourly_prices'])}, Tomorrow Prices: {len(processed_result['tomorrow_hourly_prices'])}, Cached: {processed_result['using_cached_data']}")
        return processed_result

    def _get_parser(self, source_name: str) -> Optional[BasePriceParser]:
        """Get the appropriate parser instance based on the source name."""
        # Import parsers here to avoid circular dependencies
        from ..api.parsers.entsoe_parser import EntsoeParser
        from ..api.parsers.nordpool_parser import NordpoolPriceParser
        from ..api.parsers.stromligning_parser import StromligningParser
        from ..api.parsers.energi_data_parser import EnergiDataParser
        from ..api.parsers.omie_parser import OmieParser
        from ..api.parsers.aemo_parser import AemoParser
        from ..api.parsers.epex_parser import EpexParser
        # Add other parsers as needed
        # ...

        parser_map = {
            # Use API Class names as keys, matching what FallbackManager provides
            "EntsoeAPI": EntsoeParser,
            "NordpoolAPI": NordpoolPriceParser,
            # Add mapping for Stromligning
            "StromligningAPI": StromligningParser,
            # Add mapping for EnergiDataService
            "EnergiDataAPI": EnergiDataParser,
            # Add mapping for OmieAPI
            "OmieAPI": OmieParser,
            # Add mapping for AemoAPI
            "AemoAPI": AemoParser,
            # Add mapping for EpexAPI
            "EpexAPI": EpexParser,
            # ... add mappings for other sources using their API class name ...
        }

        parser_class = parser_map.get(source_name)
        if parser_class:
            # Pass timezone_service if needed by the parser's base class
            return parser_class(timezone_service=self._tz_service)
        return None

    def _calculate_statistics(self, hourly_prices: Dict[str, float]) -> PriceStatistics:
        """Calculate price statistics from a dictionary of hourly prices (HH:00 keys)."""
        prices = [p for p in hourly_prices.values() if p is not None]
        if not prices:
            return PriceStatistics(complete_data=False)

        prices.sort()
        mid = len(prices) // 2
        # Ensure indices are valid before access
        median = None
        if prices:
            if len(prices) % 2 == 1:
                median = prices[mid]
            elif mid > 0:
                median = (prices[mid - 1] + prices[mid]) / 2
            else: # Only one element
                median = prices[0]

        return PriceStatistics(
            min=min(prices) if prices else None,
            max=max(prices) if prices else None,
            average=sum(prices) / len(prices) if prices else None,
            median=median,
            complete_data=True # Assume complete if this function is called
        )

    def _generate_empty_processed_result(self, data, error=None):
        # No need to ensure exchange service here as it doesn't use it directly
        # when generating the *initial* empty structure.
        return {
            "source": data.get("source", "unknown"),
            "area": self.area,
            "source_currency": data.get("currency"),
            "target_currency": self.target_currency,
            "source_timezone": data.get("source_timezone"),
            "target_timezone": str(self._tz_service.area_timezone) if self._tz_service else None, # Use area_timezone as suggested by error
            "hourly_prices": {},
            "tomorrow_hourly_prices": {},
            "raw_hourly_prices_original": data.get("hourly_prices"), # Store original if available
            "current_price": None,
            "next_hour_price": None,
            "current_hour_key": None,
            "next_hour_key": None,
            "statistics": PriceStatistics(complete_data=False).to_dict(),
            "tomorrow_statistics": PriceStatistics(complete_data=False).to_dict(),
            "vat_rate": self.vat_rate * 100 if self.include_vat else 0,
            "vat_included": self.include_vat,
            "display_unit": self.display_unit,
            "raw_data": data.get("raw_data"),
            "ecb_rate": None,
            "ecb_updated": None,
            "has_tomorrow_prices": False,
            "attempted_sources": data.get("attempted_sources", []),
            "fallback_sources": data.get("fallback_sources", []),
            "using_cached_data": data.get("using_cached_data", False),
            "error": error or "No data available",
            "fetched_at": data.get("fetched_at")
        }
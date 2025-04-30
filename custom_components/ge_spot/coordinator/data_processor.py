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
from custom_components.ge_spot.timezone.timezone_utils import get_timezone_object

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

        # Validate input
        if not data or not isinstance(data, dict) or not data.get("hourly_raw"):
            _LOGGER.warning(f"Invalid or empty raw data received for processing in area {self.area}. Data keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
            return self._generate_empty_processed_result(data)

        raw_hourly_prices = data["hourly_raw"]
        source_timezone = data.get("timezone")
        source_currency = data.get("currency")
        source = data.get("source_name", "unknown")
        raw_api_data = data.get("raw_data")

        if not source_timezone:
            _LOGGER.error(f"Missing 'timezone' key in raw data for source {source}. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing timezone key in raw data")
        if not source_currency:
            _LOGGER.error(f"Missing currency for source {source}. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing currency in raw data")

        # 1. Normalize timezones (convert all ISO keys to target timezone with preserved date info)
        try:
            # This will convert ISO timestamp keys to 'YYYY-MM-DD HH:00' format in target timezone
            normalized_prices = self._tz_converter.normalize_hourly_prices(
                raw_hourly_prices,
                source_timezone,
                preserve_date=True  # Keep date part for today/tomorrow split
            )

            # 2. Split into today/tomorrow using the normalized keys with dates
            normalized_today, normalized_tomorrow = self._tz_converter.split_into_today_tomorrow(normalized_prices)
            
            # Log the results of normalization and splitting
            _LOGGER.debug(f"Normalized {len(raw_hourly_prices)} timestamps into: today({len(normalized_today)}), tomorrow({len(normalized_tomorrow)})")
        except Exception as e:
            _LOGGER.error(f"Error during timestamp normalization for {self.area}: {e}", exc_info=True)
            return self._generate_empty_processed_result(data, error=f"Timestamp normalization error: {e}")

        # 3. Currency/unit conversion (one time, after normalization)
        ecb_rate = None
        ecb_updated = None
        final_today_prices = {}
        if normalized_today:
            converted_today, rate, rate_ts = await self._currency_converter.convert_hourly_prices(
                hourly_prices=normalized_today,
                source_currency=source_currency,
                source_unit=EnergyUnit.MWH
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
                source_unit=EnergyUnit.MWH
            )
            final_tomorrow_prices = converted_tomorrow
            if ecb_rate is None and rate is not None:
                ecb_rate = rate
                ecb_updated = rate_ts

        # 4. Build result
        processed_result = {
            "source": source,
            "area": self.area,
            "source_currency": source_currency,
            "target_currency": self.target_currency,
            "source_timezone": source_timezone,
            "target_timezone": str(self._tz_service.target_timezone) if self._tz_service else None,
            "hourly_prices": final_today_prices,
            "tomorrow_hourly_prices": final_tomorrow_prices,
            "raw_hourly_prices_original": raw_hourly_prices,
            "current_price": None,
            "next_hour_price": None,
            "current_hour_key": None,
            "next_hour_key": None,
            "statistics": PriceStatistics(complete_data=False).to_dict(),
            "tomorrow_statistics": PriceStatistics(complete_data=False).to_dict(),
            "vat_rate": self.vat_rate * 100 if self.include_vat else 0,
            "vat_included": self.include_vat,
            "display_unit": self.display_unit,
            "raw_data": raw_api_data,
            "ecb_rate": ecb_rate,
            "ecb_updated": ecb_updated,
            "has_tomorrow_prices": bool(final_tomorrow_prices),
            "attempted_sources": data.get("attempted_sources", []),
            "fallback_sources": data.get("fallback_sources", []),
            "using_cached_data": data.get("using_cached_data", False),
            "fetched_at": data.get("fetched_at")
        }

        # Calculate statistics and current/next hour prices as before...
        try:
            # 3a. Calculate Today's Statistics and Current/Next Prices
            if final_today_prices:
                current_hour_key = self._tz_service.get_current_hour_key()
                next_hour_key = self._tz_service.get_next_hour_key()
                processed_result["current_hour_key"] = current_hour_key
                processed_result["next_hour_key"] = next_hour_key
                processed_result["current_price"] = final_today_prices.get(current_hour_key)
                processed_result["next_hour_price"] = final_today_prices.get(next_hour_key)

                today_keys = set(self._tz_service.get_today_range())
                found_keys = set(final_today_prices.keys())
                today_complete = today_keys.issubset(found_keys)

                if today_complete:
                    stats = self._calculate_statistics(final_today_prices)
                    stats.complete_data = True
                    processed_result["statistics"] = stats.to_dict()
                    _LOGGER.debug(f"Calculated today's statistics for {self.area}")
                else:
                    missing_keys = sorted(list(today_keys - found_keys))
                    _LOGGER.warning(f"Incomplete data for today ({len(found_keys)}/{len(today_keys)} keys found, missing: {missing_keys}), skipping statistics calculation for {self.area}.")
                    processed_result["statistics"] = PriceStatistics(complete_data=False).to_dict()
            else:
                _LOGGER.warning(f"No final prices for today available after processing for area {self.area}, skipping stats.")
                processed_result["statistics"] = PriceStatistics(complete_data=False).to_dict()

            # 3b. Calculate Tomorrow's Statistics
            if final_tomorrow_prices:
                tomorrow_keys = set(self._tz_service.get_tomorrow_range())
                found_keys = set(final_tomorrow_prices.keys())
                tomorrow_complete = tomorrow_keys.issubset(found_keys)

                if tomorrow_complete:
                    stats = self._calculate_statistics(final_tomorrow_prices)
                    stats.complete_data = True
                    processed_result["tomorrow_statistics"] = stats.to_dict()
                    _LOGGER.debug(f"Calculated tomorrow's statistics for {self.area}")
                else:
                    missing_keys = sorted(list(tomorrow_keys - found_keys))
                    _LOGGER.warning(f"Incomplete data for tomorrow ({len(found_keys)}/{len(tomorrow_keys)} keys found, missing: {missing_keys}), skipping statistics calculation for {self.area}.")
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

        _LOGGER.info(f"Successfully processed data for area {self.area}. Source: {source}, Today Prices: {len(processed_result['hourly_prices'])}, Tomorrow Prices: {len(processed_result['tomorrow_hourly_prices'])}, Cached: {processed_result['using_cached_data']}")
        return processed_result

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
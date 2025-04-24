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
        exchange_service: ExchangeRateService
    ):
        """Initialize the data processor.

        Args:
            hass: Home Assistant instance
            area: Area code
            target_currency: Target currency code
            config: Configuration dictionary
            tz_service: Timezone service instance
            exchange_service: Exchange rate service instance
        """
        self.hass = hass
        self.area = area
        self.target_currency = target_currency
        self.config = config
        self._tz_service = tz_service
        self._exchange_service = exchange_service
        
        # Extract config settings needed for processing
        self.vat_rate = config.get(Config.VAT, Defaults.VAT_RATE) / 100  # Convert % to rate
        self.include_vat = config.get(Config.INCLUDE_VAT, Defaults.INCLUDE_VAT)
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS

    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the selected source data: Normalize timezone, convert currency, calculate stats."""
        
        _LOGGER.debug(f"Processing data for area {self.area} from source {data.get('source')}")
        
        # Basic validation
        if not data or not isinstance(data, dict) or not data.get("hourly_prices"):
            _LOGGER.warning(f"Invalid or empty data received for processing in area {self.area}. Data keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
            return self._generate_empty_processed_result(data)

        # Extract key info from input data (result of fetch_with_fallback)
        raw_hourly_prices = data.get("hourly_prices", {})
        source_timezone = data.get("api_timezone")
        source_currency = data.get("currency")
        source = data.get("source", "unknown")
        raw_api_data = data.get("raw_data") # Keep raw data if available
        has_tomorrow_prices_flag = data.get("has_tomorrow_prices", False) # Flag from parser/fetcher

        if not source_timezone:
            _LOGGER.error(f"Missing source timezone for source {source}. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing source timezone")
            
        if not source_currency:
            _LOGGER.error(f"Missing source currency for source {source}. Cannot process.")
            return self._generate_empty_processed_result(data, error="Missing source currency")

        processed_result = { 
            "source": source,
            "area": self.area,
            "source_currency": source_currency,
            "target_currency": self.target_currency,
            "source_timezone": source_timezone,
            "target_timezone": str(self._tz_service.ha_timezone), # Assuming HA time is the target
            "hourly_prices": {}, # Today's FINAL prices (HH:00 keys)
            "tomorrow_hourly_prices": {}, # Tomorrow's FINAL prices (HH:00 keys)
            "raw_hourly_prices_normalized_today": {}, # Optional intermediate step
            "raw_hourly_prices_normalized_tomorrow": {}, # Optional intermediate step
            "raw_hourly_prices_original": raw_hourly_prices, # Store original parser output
            "current_price": None,
            "next_hour_price": None,
            "current_hour_key": None,
            "next_hour_key": None,
            "statistics": PriceStatistics(complete_data=False).to_dict(), # Today's stats
            "tomorrow_statistics": PriceStatistics(complete_data=False).to_dict(), # Tomorrow's stats
            "vat_rate": self.vat_rate * 100 if self.include_vat else 0,
            "vat_included": self.include_vat,
            "display_unit": self.display_unit,
            "raw_data": raw_api_data,
            "ecb_rate": None,
            "ecb_updated": None,
            "has_tomorrow_prices": False, # This will be set based on processed tomorrow data
            # Pass through tracking info from fetch_with_fallback
            "attempted_sources": data.get("attempted_sources", []),
            "fallback_sources": data.get("fallback_sources", []),
            "using_cached_data": data.get("using_cached_data", False),
            "fetched_at": data.get("fetched_at")
        }

        try:
            # 1. Normalize Timezones
            # This returns {"today": {...}, "tomorrow": {...}, "other": {...}}
            # Keys in the inner dicts are HH:00 in HA timezone
            normalized_data = self._tz_service.normalize_hourly_prices(raw_hourly_prices, source_timezone)
            normalized_today = normalized_data.get("today", {})
            normalized_tomorrow = normalized_data.get("tomorrow", {})
            processed_result["raw_hourly_prices_normalized_today"] = normalized_today
            processed_result["raw_hourly_prices_normalized_tomorrow"] = normalized_tomorrow
            _LOGGER.debug(f"Normalized prices: {len(normalized_today)} today, {len(normalized_tomorrow)} tomorrow")

            # Helper Function for Currency Conv/VAT/Subunit
            async def process_price(price, source_curr, target_curr):
                if price is None: return None
                # Convert currency
                converted = await self._exchange_service.convert(price, source_curr, target_curr)
                # Apply VAT
                if self.include_vat:
                    converted *= (1 + self.vat_rate)
                # Handle subunit
                if self.use_subunit:
                    if target_curr in [Currency.EUR, Currency.USD, Currency.GBP, Currency.SEK, Currency.NOK, Currency.DKK]: 
                        converted *= 100
                    else:
                        _LOGGER.warning(f"Subunit conversion not implemented for {target_curr}, using base unit.")
                return converted

            # 2a. Process Today's Prices
            final_today_prices = {}
            for hour_key, price in normalized_today.items():
                final_today_prices[hour_key] = await process_price(price, source_currency, self.target_currency)
            processed_result["hourly_prices"] = final_today_prices
            _LOGGER.debug(f"Processed {len(final_today_prices)} prices for today")

            # 2b. Process Tomorrow's Prices
            final_tomorrow_prices = {}
            if normalized_tomorrow:
                for hour_key, price in normalized_tomorrow.items():
                    final_tomorrow_prices[hour_key] = await process_price(price, source_currency, self.target_currency)
                processed_result["tomorrow_hourly_prices"] = final_tomorrow_prices
                processed_result["has_tomorrow_prices"] = True # Set flag based on processed data
                _LOGGER.debug(f"Processed {len(final_tomorrow_prices)} prices for tomorrow")
            else:
                processed_result["has_tomorrow_prices"] = False

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
            # Return structure with error, preserving original raw data if possible
            error_result = self._generate_empty_processed_result(data, error=str(e))
            error_result["raw_hourly_prices_original"] = raw_hourly_prices # Keep original raw input
            return error_result
            
        # Add ECB rate info for attributes
        try:
            # Use source_currency for base if not EUR?
            # The service currently assumes EUR base for ECB, might need adjustment if source_currency != EUR
            base_curr = Currency.EUR if source_currency == Currency.EUR else source_currency 
            ecb_info = self._exchange_service.get_exchange_rate_info(base_curr, self.target_currency)
            processed_result["ecb_rate"] = ecb_info.get("formatted")
            processed_result["ecb_updated"] = ecb_info.get("timestamp")
        except Exception as e:
            _LOGGER.warning(f"Could not get ECB info: {e}")
            # Keep default None values

        _LOGGER.info(f"Successfully processed data for area {self.area}. Source: {source}, Today Prices: {len(processed_result['hourly_prices'])}, Tomorrow Prices: {len(processed_result['tomorrow_hourly_prices'])}")
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
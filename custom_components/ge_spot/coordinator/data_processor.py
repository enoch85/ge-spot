"""Data processor for electricity spot prices."""

import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..utils.exchange_service import ExchangeRateService
from ..const.config import Config
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.time import TimeInterval
from ..const.sources import Source
from ..const.attributes import Attributes
from ..const.energy import EnergyUnit
from ..timezone.service import TimezoneService
from ..api.base.data_structure import PriceStatistics
from ..timezone.timezone_converter import TimezoneConverter
from ..price.currency_converter import CurrencyConverter
from ..api.base.price_parser import BasePriceParser
from .data_validity import DataValidity, calculate_data_validity, parse_interval_key

# Parser imports for get_parser method
from ..api.parsers.entsoe_parser import EntsoeParser
from ..api.parsers.nordpool_parser import NordpoolParser
from ..api.parsers.stromligning_parser import StromligningParser
from ..api.parsers.energi_data_parser import EnergiDataParser
from ..api.parsers.omie_parser import OmieParser
from ..api.parsers.aemo_parser import AemoParser
from ..api.parsers.energy_charts_parser import EnergyChartsParser
from ..api.parsers.comed_parser import ComedParser
from ..api.parsers.amber_parser import AmberParser

_LOGGER = logging.getLogger(__name__)


def parse_interval_key(interval_key: str) -> tuple[int, int]:
    """Parse interval key to hour and minute, handling DST suffixes.

    Args:
        interval_key: Key in format "HH:MM" or "HH:MM_1" or "HH:MM_2"

    Returns:
        Tuple of (hour, minute)

    Raises:
        ValueError: If key format is invalid

    Examples:
        >>> parse_interval_key("14:30")
        (14, 30)
        >>> parse_interval_key("02:15_1")
        (2, 15)
        >>> parse_interval_key("02:15_2")
        (2, 15)
    """
    # Match format: HH:MM optionally followed by _1 or _2
    # This is strict - only allows valid DST suffixes, not any arbitrary suffix
    match = re.match(r"^(\d{1,2}):(\d{2})(?:_[12])?$", interval_key)

    if not match:
        raise ValueError(
            f"Invalid interval key format: '{interval_key}' (expected HH:MM or HH:MM_1 or HH:MM_2)"
        )

    hour = int(match.group(1))
    minute = int(match.group(2))

    # Validate ranges
    if not (0 <= hour <= 23):
        raise ValueError(f"Hour must be 0-23, got {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"Minute must be 0-59, got {minute}")

    return hour, minute


# NOTE: All API modules should return raw, unprocessed data in this standardized format:
# {
#     "today_interval_prices": {"HH:MM" or ISO: price, ...},
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
        manager: Any,
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
        # VAT is already stored as a decimal rate (e.g., 0.25 for 25%), not as a percentage
        self.vat_rate = config.get(Config.VAT, Defaults.VAT)
        # Smart VAT inclusion: if VAT rate is configured (> 0), automatically apply it
        # This makes the behavior intuitive - configuring a VAT rate implies you want it applied
        configured_include_vat = config.get(Config.INCLUDE_VAT, Defaults.INCLUDE_VAT)
        self.include_vat = configured_include_vat or (self.vat_rate > 0)
        self.additional_tariff = config.get(
            Config.ADDITIONAL_TARIFF, Defaults.ADDITIONAL_TARIFF
        )
        self.energy_tax = config.get(Config.ENERGY_TAX, Defaults.ENERGY_TAX)
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
        # Use Defaults.PRECISION instead of DEFAULT_PRICE_PRECISION
        self.precision = config.get(Config.PRECISION, Defaults.PRECISION)

        # Log VAT configuration for transparency
        if self.include_vat:
            _LOGGER.debug(
                f"[{area}] VAT will be applied: {self.vat_rate * 100:.1f}% "
                f"(auto-enabled: {not configured_include_vat and self.vat_rate > 0})"
            )
        else:
            _LOGGER.debug(f"[{area}] VAT disabled (rate: {self.vat_rate * 100:.1f}%)")

        # Instantiate converters
        self._tz_converter = TimezoneConverter(tz_service)
        # CurrencyConverter needs exchange service, which is async, handle in process
        self._currency_converter: Optional[CurrencyConverter] = None

    async def _ensure_exchange_service(self):
        """Ensure the exchange service is available from the manager."""
        if self._exchange_service is None:
            # Check if the _manager is already an ExchangeRateService (for tests)
            if hasattr(self._manager, "get_rates"):
                self._exchange_service = self._manager
                await self._exchange_service.get_rates()  # Initialize the rates
            # Manager with _exchange_service attribute (normal operation)
            elif (
                hasattr(self._manager, "_exchange_service")
                and self._manager._exchange_service is not None
            ):
                self._exchange_service = self._manager._exchange_service
            # Manager with _ensure_exchange_service method (normal operation)
            elif hasattr(self._manager, "_ensure_exchange_service"):
                await self._manager._ensure_exchange_service()
                self._exchange_service = self._manager._exchange_service
            else:
                _LOGGER.error("Exchange service not available in DataProcessor")
                raise RuntimeError(
                    "Exchange service could not be initialized or retrieved."
                )

        # Instantiate CurrencyConverter once exchange service is ready
        if self._currency_converter is None and self._exchange_service is not None:
            self._currency_converter = CurrencyConverter(
                exchange_service=self._exchange_service,
                target_currency=self.target_currency,
                display_unit=self.display_unit,
                include_vat=self.include_vat,
                vat_rate=self.vat_rate,
                additional_tariff=self.additional_tariff,
                energy_tax=self.energy_tax,
            )

        # Ensure we have a valid currency converter
        if self._currency_converter is None:
            _LOGGER.error("Failed to initialize currency converter")
            raise RuntimeError("Currency converter could not be initialized.")

    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Accepts raw data from API adapter (e.g. entsoe.py)
        # Expects keys: 'interval_raw', 'timezone', 'currency', 'source_name', ...
        await self._ensure_exchange_service()

        source_name = data.get("data_source") or data.get("source")
        is_cached_data = data.get("using_cached_data", False)

        input_interval_raw: Optional[Dict[str, Any]] = None
        input_source_timezone: Optional[str] = None
        input_source_currency: Optional[str] = None
        parser_current_price: Optional[float] = None
        parser_next_price: Optional[float] = None
        raw_api_data_for_result = (
            data.get("raw_data")
            or data.get("xml_responses")
            or data.get("dict_response")
        )

        if not source_name:
            _LOGGER.error(
                f"Missing 'data_source' or 'source' key in input data for area {self.area}. Cannot determine parser."
            )
            return self._generate_empty_processed_result(
                data, error="Missing source identifier"
            )

        if is_cached_data:
            _LOGGER.debug(
                f"[{self.area}] Processing cached data from source '{source_name}'."
            )

            # Check if we have already-processed price data
            cached_today = data.get("today_interval_prices", {})
            cached_tomorrow = data.get("tomorrow_interval_prices", {})

            # Cached data is valid if we have today OR tomorrow prices
            # Current interval may be historical (after 13:00 day-ahead publication)
            # and not present in the data - this is EXPECTED behavior
            has_valid_cached_data = bool(cached_today or cached_tomorrow)

            if has_valid_cached_data:
                # Use already-split data from cache - validated and safe
                current_interval_key = self._tz_service.get_current_interval_key()
                has_current_interval = current_interval_key in cached_today
                _LOGGER.debug(
                    f"[{self.area}] Using already-processed prices from cache "
                    f"(today={len(cached_today)}, tomorrow={len(cached_tomorrow)}, "
                    f"current interval present: {has_current_interval})"
                )

                # Extract metadata from cache
                input_source_timezone = data.get("source_timezone")
                input_source_currency = data.get("source_currency")
                # Preserve the original raw prices from cache for storage
                input_interval_raw = data.get("raw_interval_prices_original", {})

                # IMPORTANT: Cached data is already currency-converted and VAT-applied
                # Use as final prices directly - do NOT re-normalize or re-convert
                final_today_prices = cached_today
                final_tomorrow_prices = cached_tomorrow

                # Extract raw prices from cache (added for Issue #40)
                raw_today_prices = data.get("today_raw_prices", {})
                raw_tomorrow_prices = data.get("tomorrow_raw_prices", {})

                # Preserve exchange rate info from cache
                ecb_rate = data.get("ecb_rate")
                ecb_updated = data.get("ecb_updated")

                # Set flag to skip normalization AND currency conversion steps
                skip_normalization = True
                skip_currency_conversion = True

            else:
                # Fallback to raw processing if no processed prices in cache
                _LOGGER.warning(
                    f"[{self.area}] Cached data has no processed prices "
                    f"(today={len(cached_today)}, tomorrow={len(cached_tomorrow)}), "
                    f"falling back to raw reprocessing"
                )

                skip_normalization = False
                skip_currency_conversion = False

                # For cached data, we expect 'raw_interval_prices_original', 'source_timezone', and 'source_currency'
                # These represent the state *before* previous normalization and conversion.
                if (
                    "raw_interval_prices_original" in data
                    and "source_timezone" in data
                    and "source_currency" in data
                ):
                    input_interval_raw = data.get("raw_interval_prices_original")
                    input_source_timezone = data.get("source_timezone")
                    input_source_currency = data.get("source_currency")
                    _LOGGER.debug(
                        f"[{self.area}] Using 'raw_interval_prices_original' from cache for reprocessing."
                    )

                    # Ensure raw_api_data_for_result is also populated from cache if it exists there
                    # The initial raw_api_data_for_result might be from the top-level cache dict,
                    # but the more specific one might be nested if the cache stores the full processed dict.
                    if data.get("raw_data"):
                        raw_api_data_for_result = data.get("raw_data")

                else:
                    _LOGGER.warning(
                        f"[{self.area}] Cached data for '{source_name}' is missing expected fields: 'raw_interval_prices_original', 'source_timezone', or 'source_currency'. Attempting to re-parse, but this may lead to errors if data is already processed."
                    )
                    # Fallback to trying to parse the main 'interval_prices' if the original raw is missing (old cache format)
                    # This is risky and might be what was causing issues.
                    # The EntsoeParser change should make it safer as it will look for XML.
                    parser = self._get_parser(source_name)
                    if not parser:
                        _LOGGER.error(
                            f"No parser found for source '{source_name}' in area {self.area} during cached data processing."
                        )
                        return self._generate_empty_processed_result(
                            data,
                            error=f"No parser for source {source_name} (cache path)",
                        )
                    try:
                        # Pass the entire cached dictionary to the parser.
                        # The modified EntsoeParser will look for XML within this dict.
                        parsed_data = parser.parse(data)

                        # Validate parsed data (checks structural integrity only)
                        if hasattr(
                            parser, "validate_parsed_data"
                        ) and not parser.validate_parsed_data(parsed_data):
                            # Validation failed - data structure is invalid
                            _LOGGER.debug(
                                f"[{self.area}] Cached data validation failed for source '{source_name}' - treating as invalid cache"
                            )
                            return self._generate_empty_processed_result(
                                data,
                                error=f"Cached data validation failed: invalid data structure",
                            )

                        input_interval_raw = parsed_data.get("interval_raw")
                        input_source_timezone = parsed_data.get("timezone")
                        input_source_currency = parsed_data.get("currency")
                        # If parser extracted metadata (like raw_data from within), use it
                        if parsed_data.get("raw_data"):
                            raw_api_data_for_result = parsed_data.get("raw_data")
                        _LOGGER.debug(
                            f"[{self.area}] Reparsed cached data with {parser.__class__.__name__}. Got {len(input_interval_raw if input_interval_raw else {})} raw prices."
                        )
                    except Exception as parse_err:
                        _LOGGER.error(
                            f"[{self.area}] Error re-parsing cached data from source '{source_name}': {parse_err}",
                            exc_info=True,
                        )
                        return self._generate_empty_processed_result(
                            data, error=f"Cache re-parsing error: {parse_err}"
                        )
        else:
            skip_normalization = False
            skip_currency_conversion = False
            # --- Fresh Data: Step 1: Parse Raw Data ---
            _LOGGER.debug(
                f"[{self.area}] Processing fresh (non-cached) data from source '{source_name}'."
            )
            parser = self._get_parser(source_name)
            if not parser:
                _LOGGER.error(
                    f"No parser found for source '{source_name}' in area {self.area}."
                )
                return self._generate_empty_processed_result(
                    data, error=f"No parser for source {source_name}"
                )

            try:
                # Pass the entire raw dictionary from FallbackManager/API Adapter to the parser
                parsed_data = parser.parse(data)
                _LOGGER.debug(
                    f"[{self.area}] Parser {parser.__class__.__name__} output keys: {list(parsed_data.keys())}"
                )

                # Validate parsed data (checks structural integrity only)
                if hasattr(
                    parser, "validate_parsed_data"
                ) and not parser.validate_parsed_data(parsed_data):
                    # Validation failed - data structure is invalid, trigger fallback to next source
                    _LOGGER.debug(
                        f"[{self.area}] Parsed data validation failed for source '{source_name}' - triggering fallback to next source"
                    )
                    return self._generate_empty_processed_result(
                        data,
                        error=f"Validation failed: source '{source_name}' returned invalid data structure",
                    )

                input_interval_raw = parsed_data.get("interval_raw")
                input_source_timezone = parsed_data.get("timezone")
                input_source_currency = parsed_data.get("currency")
                # Preserve parser-provided current/next prices (for real-time APIs like ComEd)
                parser_current_price = parsed_data.get("current_price")
                parser_next_price = parsed_data.get("next_interval_price")
                # If parser extracted metadata (like raw_data from within), use it
                if parsed_data.get("raw_data"):
                    raw_api_data_for_result = parsed_data.get("raw_data")

            except Exception as parse_err:
                _LOGGER.error(
                    f"[{self.area}] Error parsing fresh data from source '{source_name}': {parse_err}",
                    exc_info=True,
                )
                return self._generate_empty_processed_result(
                    data, error=f"Parsing error: {parse_err}"
                )

        # --- Validate inputs for normalization (skip if using processed cache) ---
        if not skip_normalization:
            if not input_interval_raw or not isinstance(input_interval_raw, dict):
                _LOGGER.warning(
                    f"[{self.area}] No valid 'interval_raw' data available for source '{source_name}' after parsing/cache handling. Cached: {is_cached_data}"
                )
                return self._generate_empty_processed_result(
                    data, error=f"No interval_raw data from {source_name}"
                )

            if not input_source_timezone:
                _LOGGER.error(
                    f"Missing 'timezone' for source {source_name} after parsing/cache handling. Cannot process. Cached: {is_cached_data}"
                )
                return self._generate_empty_processed_result(
                    data, error="Missing timezone after parsing/cache handling"
                )
            if not input_source_currency:
                _LOGGER.error(
                    f"Missing currency for source {source_name} after parsing/cache handling. Cannot process. Cached: {is_cached_data}"
                )
                return self._generate_empty_processed_result(
                    data, error="Missing currency after parsing/cache handling"
                )

        # --- Step 2: Normalize Timezones (skip if using processed cache) ---
        if not skip_normalization:
            try:
                # This will convert ISO timestamp keys to 'YYYY-MM-DD HH:MM' format in target timezone
                normalized_prices = self._tz_converter.normalize_interval_prices(
                    input_interval_raw,  # Use the determined input_interval_raw
                    input_source_timezone,  # Use the determined input_source_timezone
                    preserve_date=True,  # Keep date part for today/tomorrow split
                )

                # Split into today/tomorrow using the normalized keys with dates
                normalized_today, normalized_tomorrow = (
                    self._tz_converter.split_into_today_tomorrow(normalized_prices)
                )

                # Log the results of normalization and splitting
                _LOGGER.debug(
                    f"Normalized {len(input_interval_raw)} timestamps from {input_source_timezone} into target TZ. Today: {len(normalized_today)}, Tomorrow: {len(normalized_tomorrow)} prices."
                )
            except Exception as e:
                _LOGGER.error(
                    f"Error during timestamp normalization for {self.area} (source_tz: {input_source_timezone}): {e}",
                    exc_info=True,
                )
                _LOGGER.debug(
                    f"Data passed to normalize_interval_prices that failed: {input_interval_raw}"
                )  # Log problematic data
                return self._generate_empty_processed_result(
                    data, error=f"Timestamp normalization error: {e}"
                )
        else:
            # Using already-processed cache - normalized_today and normalized_tomorrow already set
            _LOGGER.debug(
                f"[{self.area}] Skipping normalization - using already-processed cache data"
            )

        # --- Step 3: Currency/Unit Conversion (skip if using processed cache) ---
        if not skip_currency_conversion:
            ecb_rate = None
            ecb_updated = None
            final_today_prices = {}
            raw_today_prices = {}  # Store raw prices (without VAT/taxes/tariffs)
            # Get source unit from the input data, default to MWh if not present
            # For cached data, this might be inside the 'data' dict, or from the original fetch context
            source_unit = data.get("source_unit", EnergyUnit.MWH)
            _LOGGER.debug(
                f"[{self.area}] Using source unit '{source_unit}' for currency conversion."
            )

            if normalized_today:
                converted_today, raw_today, rate, rate_ts = (
                    await self._currency_converter.convert_interval_prices(
                        interval_prices=normalized_today,
                        source_currency=input_source_currency,  # Use determined input_source_currency
                        # Pass the determined source_unit
                        source_unit=source_unit,
                    )
                )
                final_today_prices = converted_today
                raw_today_prices = raw_today
                if rate is not None:
                    ecb_rate = rate
                    ecb_updated = rate_ts
            final_tomorrow_prices = {}
            raw_tomorrow_prices = {}  # Store raw prices (without VAT/taxes/tariffs)
            if normalized_tomorrow:
                converted_tomorrow, raw_tomorrow, rate, rate_ts = (
                    await self._currency_converter.convert_interval_prices(
                        interval_prices=normalized_tomorrow,
                        source_currency=input_source_currency,  # Use determined input_source_currency
                        # Pass the determined source_unit
                        source_unit=source_unit,
                    )
                )
                final_tomorrow_prices = converted_tomorrow
                raw_tomorrow_prices = raw_tomorrow
                if ecb_rate is None and rate is not None:
                    ecb_rate = rate
                    ecb_updated = rate_ts
        else:
            # Using already-processed cache - final prices and ECB rate already set
            _LOGGER.debug(
                f"[{self.area}] Skipping currency conversion - using already-converted cache data"
            )

        # --- Step 4: Build Result ---
        processed_result = {
            "source": source_name,  # Use source_name identified earlier
            "area": self.area,
            "source_currency": input_source_currency,  # Store the actual source currency used
            "target_currency": self.target_currency,
            "source_timezone": input_source_timezone,  # Store the actual source timezone used
            "target_timezone": (
                str(self._tz_service.target_timezone) if self._tz_service else None
            ),
            "today_interval_prices": final_today_prices,
            "tomorrow_interval_prices": final_tomorrow_prices,
            "today_raw_prices": raw_today_prices,  # Raw prices without VAT/taxes/tariffs
            "tomorrow_raw_prices": raw_tomorrow_prices,  # Raw prices without VAT/taxes/tariffs
            "raw_interval_prices_original": input_interval_raw,  # Store the raw prices that went INTO normalization
            "current_price": None,
            "next_interval_price": None,
            "current_interval_key": None,
            "next_interval_key": None,
            "statistics": PriceStatistics().to_dict(),
            "tomorrow_statistics": PriceStatistics().to_dict(),
            "vat_rate": self.vat_rate * 100 if self.include_vat else 0,
            "vat_included": self.include_vat,
            "display_unit": self.display_unit,
            "raw_data": raw_api_data_for_result,  # Store original raw API data (XML, JSON, etc.)
            "ecb_rate": ecb_rate,
            "ecb_updated": ecb_updated,
            "has_tomorrow_prices": bool(final_tomorrow_prices),
            "attempted_sources": data.get("attempted_sources", []),
            "fallback_sources": data.get("fallback_sources", []),
            "using_cached_data": is_cached_data,  # Reflect if this cycle used cache
            "fetched_at": data.get("fetched_at"),
        }

        # --- Add Stromligning Attribution ---
        if source_name == Source.STROMLIGNING:
            processed_result[Attributes.DATA_SOURCE_ATTRIBUTION] = (
                "Data provided by Strømligning. https://stromligning.dk"
            )
        # --- End Attribution ---

        # Initialize tomorrow_valid flag
        processed_result["tomorrow_valid"] = False

        # --- Step 5: Calculate Statistics and Current/Next Prices ---
        try:
            # Calculate Today's Statistics and Current/Next Prices
            if final_today_prices:
                current_interval_key = self._tz_service.get_current_interval_key()
                next_interval_key = self._tz_service.get_next_interval_key()
                processed_result["current_interval_key"] = current_interval_key
                processed_result["next_interval_key"] = next_interval_key

                # Use parser-provided current price if available (for real-time APIs like ComEd)
                # Otherwise, look up the price for the current interval key
                if (
                    not is_cached_data
                    and "parser_current_price" in locals()
                    and parser_current_price is not None
                ):
                    processed_result["current_price"] = parser_current_price
                    _LOGGER.debug(
                        f"[{self.area}] Using parser-provided current price: {parser_current_price} "
                        f"(source: {source_name})"
                    )
                else:
                    processed_result["current_price"] = final_today_prices.get(
                        current_interval_key
                    )

                # Use parser-provided next price if available
                if (
                    not is_cached_data
                    and "parser_next_price" in locals()
                    and parser_next_price is not None
                ):
                    processed_result["next_interval_price"] = parser_next_price
                else:
                    processed_result["next_interval_price"] = final_today_prices.get(
                        next_interval_key
                    )

                # Fallback for interval-based pricing when current interval doesn't exist yet
                # This handles cases where we have interval data but the current interval is incomplete
                if (
                    processed_result["current_price"] is None
                    and source_name == Source.COMED
                ):
                    if final_today_prices:
                        # Get the most recent available price (latest time key)
                        most_recent_key = max(final_today_prices.keys())
                        processed_result["current_price"] = final_today_prices[
                            most_recent_key
                        ]
                        _LOGGER.debug(
                            f"[{self.area}] ComEd: Current interval '{current_interval_key}' not available. "
                            f"Using most recent price from interval '{most_recent_key}': {processed_result['current_price']}"
                        )

                today_keys = set(self._tz_service.get_today_range())
                found_keys = set(final_today_prices.keys())
                # Allow statistics if at least 80% of intervals are present
                # Use DST-aware interval counting for today's date
                today_date = dt_util.now(self._tz_service.area_timezone)
                expected_intervals = TimeInterval.get_expected_intervals_for_date(
                    today_date, self._tz_service.area_timezone
                )
                today_complete_enough = len(found_keys) >= math.ceil(
                    expected_intervals * 0.8
                )

                if today_complete_enough:
                    stats = self._calculate_statistics(final_today_prices, day_offset=0)
                    # Mark as complete only if all intervals are present
                    processed_result["statistics"] = stats.to_dict()
                    _LOGGER.debug(
                        f"Calculated today's statistics for {self.area}: {processed_result['statistics']}"
                    )  # Log today's stats
                else:
                    missing_keys = sorted(list(today_keys - found_keys))
                    # Update warning message threshold
                    _LOGGER.info(
                        f"Insufficient data for today ({len(found_keys)}/{len(today_keys)} keys found, need {math.ceil(expected_intervals * 0.8)}), skipping statistics calculation for {self.area}. Missing: {missing_keys[:10]}{'...' if len(missing_keys) > 10 else ''}"
                    )
                    processed_result["statistics"] = PriceStatistics().to_dict()
            else:
                _LOGGER.info(
                    f"No final prices for today available after processing for area {self.area}, skipping stats."
                )
                processed_result["statistics"] = PriceStatistics().to_dict()

            # Calculate Tomorrow's Statistics
            if final_tomorrow_prices:
                tomorrow_keys = set(self._tz_service.get_tomorrow_range())
                found_keys = set(final_tomorrow_prices.keys())
                # Allow statistics if at least 80% of intervals are present
                # Use DST-aware interval counting for tomorrow's date
                tomorrow_date = dt_util.now(self._tz_service.area_timezone) + timedelta(
                    days=1
                )
                # Reconvert to timezone to update DST offset after timedelta
                tomorrow_date = tomorrow_date.astimezone(
                    self._tz_service.area_timezone
                )
                expected_intervals = TimeInterval.get_expected_intervals_for_date(
                    tomorrow_date, self._tz_service.area_timezone
                )
                tomorrow_complete_enough = len(found_keys) >= math.ceil(
                    expected_intervals * 0.8
                )

                if tomorrow_complete_enough:
                    stats = self._calculate_statistics(
                        final_tomorrow_prices, day_offset=1
                    )
                    # Mark as complete only if all intervals are present
                    processed_result["tomorrow_statistics"] = stats.to_dict()
                    # Set tomorrow_valid if we have enough data for stats, even if not fully complete
                    processed_result["tomorrow_valid"] = True
                    _LOGGER.debug(
                        f"Calculated tomorrow's statistics for {self.area}: {processed_result['tomorrow_statistics']}"
                    )  # Log tomorrow's stats
                else:
                    missing_keys = sorted(list(tomorrow_keys - found_keys))

                    # Time-aware validation: Use DEBUG before publication time, WARNING after
                    now_utc = dt_util.utcnow()
                    publication_hour_utc = Source.get_publication_time_utc(
                        self.source if hasattr(self, "source") else "unknown"
                    )
                    data_should_be_available = now_utc.hour >= publication_hour_utc

                    log_message = (
                        f"Insufficient data for tomorrow ({len(found_keys)}/{len(tomorrow_keys)} keys found, "
                        f"need {math.ceil(expected_intervals * 0.8)}), skipping statistics calculation for {self.area}. "
                        f"Missing: {missing_keys[:10]}{'...' if len(missing_keys) > 10 else ''}"
                    )

                    if data_should_be_available:
                        # After publication time - this is concerning
                        _LOGGER.warning(
                            f"{log_message} (after expected publication time {publication_hour_utc}:00 UTC)"
                        )
                    else:
                        # Before publication time - this is expected
                        _LOGGER.debug(
                            f"{log_message} (before publication time {publication_hour_utc}:00 UTC, this is normal)"
                        )

                    processed_result["tomorrow_statistics"] = (
                        PriceStatistics().to_dict()
                    )
            else:
                # No tomorrow prices, ensure stats reflect incompleteness
                processed_result["tomorrow_statistics"] = PriceStatistics().to_dict()

        except Exception as e:
            _LOGGER.error(
                f"Error during data processing for area {self.area}: {e}", exc_info=True
            )
            # Ensure exchange service is ready even on error path
            try:
                await self._ensure_exchange_service()
            except Exception as init_err:
                _LOGGER.error(
                    f"Failed to ensure exchange service during error handling: {init_err}"
                )
            # Return structure with error, preserving original raw data if possible
            error_result = self._generate_empty_processed_result(data, error=str(e))
            error_result["raw_interval_prices_original"] = (
                input_interval_raw  # Keep original raw input
            )
            return error_result

        # Ensure source_timezone is always set in processed_result
        if not processed_result.get("source_timezone"):
            _LOGGER.error(
                f"Source timezone ('source_timezone') is missing in the processed result for area {self.area} after processing. This indicates an issue."
            )
            processed_result["error"] = (
                processed_result.get("error", "")
                + " Missing source timezone after processing."
            )

        # --- Step 6: Calculate Data Validity ---
        # This tracks how far into the future we have valid price data
        try:
            now = dt_util.now()
            current_interval_key = (
                processed_result.get("current_interval_key")
                or self._tz_service.get_current_interval_key()
            )
            # The interval_prices keys are already in target_timezone, so use that for validity timestamps
            target_timezone = str(self._tz_service.target_timezone)

            validity = calculate_data_validity(
                interval_prices=processed_result["today_interval_prices"],
                tomorrow_interval_prices=processed_result["tomorrow_interval_prices"],
                now=now,
                current_interval_key=current_interval_key,
                target_timezone=target_timezone,  # Keys are in this timezone
            )

            processed_result["data_validity"] = validity.to_dict()
            _LOGGER.info(f"Data validity for {self.area}: {validity}")

        except Exception as e:
            _LOGGER.error(
                f"Error calculating data validity for {self.area}: {e}", exc_info=True
            )
            # Add empty validity on error
            processed_result["data_validity"] = DataValidity().to_dict()

        _LOGGER.info(
            f"Successfully processed data for area {self.area}. Source: {source_name}, Today Prices: {len(processed_result['today_interval_prices'])}, Tomorrow Prices: {len(processed_result['tomorrow_interval_prices'])}, Cached: {processed_result['using_cached_data']}"
        )
        return processed_result

    def _get_parser(self, source_name: str) -> Optional[BasePriceParser]:
        """Get the appropriate parser instance based on the source name."""

        parser_map = {
            # Use lowercase source names from Source constants
            Source.NORDPOOL: NordpoolParser,
            Source.ENTSOE: EntsoeParser,
            Source.STROMLIGNING: StromligningParser,
            Source.ENERGI_DATA_SERVICE: EnergiDataParser,
            Source.OMIE: OmieParser,
            Source.AEMO: AemoParser,
            Source.ENERGY_CHARTS: EnergyChartsParser,
            Source.COMED: ComedParser,
            Source.AMBER: AmberParser,
            # ... add mappings for other sources using Source.* constants ...
        }

        parser_class = parser_map.get(source_name)
        if parser_class:
            # Pass timezone_service if needed by the parser's base class
            return parser_class(timezone_service=self._tz_service)
        return None

    def _calculate_statistics(
        self, interval_prices: Dict[str, float], day_offset: int = 0
    ) -> PriceStatistics:
        """Calculate price statistics from a dictionary of interval prices (HH:MM keys).

        Also calculates timestamps for min/max values by finding the interval key with those values.
        The timestamps are derived from the specified day (today + day_offset) in the HA timezone.

        Args:
            interval_prices: Dictionary of interval prices with HH:MM keys
            day_offset: Number of days offset from today (0=today, 1=tomorrow)
        """
        prices = [p for p in interval_prices.values() if p is not None]
        if not prices:
            return PriceStatistics()

        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)

        # Find timestamps for min and max prices
        # Get the first occurrence of min/max values
        min_timestamp = None
        max_timestamp = None

        # Get the target date based on day_offset
        now = dt_util.now()
        target_date = (now + timedelta(days=day_offset)).date()

        for interval_key, price in interval_prices.items():
            if price == min_price and min_timestamp is None:
                # Convert HH:MM key to full timestamp using target date
                try:
                    # Use the validation function that handles DST suffixes
                    hour, minute = parse_interval_key(interval_key)
                    timestamp_dt = datetime.combine(
                        target_date,
                        datetime.min.time().replace(hour=hour, minute=minute),
                    )
                    # Make it timezone-aware using the HA timezone
                    timestamp_dt = now.replace(
                        year=target_date.year,
                        month=target_date.month,
                        day=target_date.day,
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    )
                    min_timestamp = timestamp_dt.isoformat()
                except (ValueError, AttributeError) as e:
                    _LOGGER.warning(
                        f"Failed to convert interval key '{interval_key}' to timestamp: {e}"
                    )

            if price == max_price and max_timestamp is None:
                # Convert HH:MM key to full timestamp using target date
                try:
                    # Use the validation function that handles DST suffixes
                    hour, minute = parse_interval_key(interval_key)
                    timestamp_dt = datetime.combine(
                        target_date,
                        datetime.min.time().replace(hour=hour, minute=minute),
                    )
                    # Make it timezone-aware using the HA timezone
                    timestamp_dt = now.replace(
                        year=target_date.year,
                        month=target_date.month,
                        day=target_date.day,
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    )
                    max_timestamp = timestamp_dt.isoformat()
                except (ValueError, AttributeError) as e:
                    _LOGGER.warning(
                        f"Failed to convert interval key '{interval_key}' to timestamp: {e}"
                    )

            # Stop if we found both
            if min_timestamp and max_timestamp:
                break

        return PriceStatistics(
            avg=avg_price,
            min=min_price,
            max=max_price,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
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
            "target_timezone": (
                str(self._tz_service.area_timezone) if self._tz_service else None
            ),  # Use area_timezone as suggested by error
            "today_interval_prices": {},
            "tomorrow_interval_prices": {},
            "raw_interval_prices_original": data.get(
                "today_interval_prices"
            ),  # Store original if available
            "current_price": None,
            "next_interval_price": None,
            "current_interval_key": None,
            "next_interval_key": None,
            "statistics": PriceStatistics().to_dict(),
            "tomorrow_statistics": PriceStatistics().to_dict(),
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
            "fetched_at": data.get("fetched_at"),
        }

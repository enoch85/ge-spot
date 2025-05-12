"""Unified Price Manager for ge-spot integration."""
import logging
from datetime import timedelta, datetime, time, date
from typing import Any, Dict, Optional, List, Type, Union
import asyncio # Added for rate limiting

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.intervals import SourceIntervals
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.network import Network
from ..const.currencies import Currency
from ..api import get_sources_for_region
from ..api.base.base_price_api import BasePriceAPI
from ..api.base.data_structure import StandardizedPriceData, create_standardized_price_data
from ..api.base.session_manager import close_session
from ..timezone.service import TimezoneService # Added import
from ..utils.exchange_service import ExchangeService, get_exchange_service # Import get_exchange_service
from .data_processor import DataProcessor
from .fallback_manager import FallbackManager # Import the new FallbackManager
from .cache_manager import CacheManager # Import CacheManager

# Import all API implementations here to have them available
from ..api.nordpool import NordpoolAPI # Changed from NordpoolAdapter
from ..api.entsoe import EntsoeAPI       # Changed from EntsoeAdapter
from ..api.aemo import AemoAPI         # Changed from AemoAdapter
from ..api.epex import EpexAPI         # Changed from EpexAdapter
from ..api.energi_data import EnergiDataAdapter # Remains Adapter for now
from ..api.amber import AmberAdapter # Remains Adapter for now
from ..api.comed import ComedAdapter # Remains Adapter for now
from ..api.omie import OmieAPI         # Changed from OmieAdapter
from ..api.stromligning import StromligningAPI # Changed from StromligningAdapter


_LOGGER = logging.getLogger(__name__)

# Rate Limiting Lock
_FETCH_LOCK = asyncio.Lock()
_LAST_FETCH_TIME = {} # Dictionary to store last fetch time per area

class UnifiedPriceManager:
    """Unified manager for price data using improved standardized APIs."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        config: Dict[str, Any],
    ):
        """Initialize the unified price manager.

        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            config: Configuration dictionary
        """
        self.hass = hass
        self.area = area
        self.currency = currency
        self.config = config

        # API sources and tracking
        self._supported_sources = get_sources_for_region(area)
        self._source_priority = config.get(Config.SOURCE_PRIORITY, Source.DEFAULT_PRIORITY)
        self._active_source = None
        self._attempted_sources = []
        self._fallback_sources = [] # Keep track of sources used as fallback
        self._using_cached_data = False

        # Services and utilities
        self._tz_service = TimezoneService(hass=hass, area=area, config=config) # Initialize with all parameters
        self._fallback_manager = FallbackManager()
        self._cache_manager = CacheManager(hass=hass, config=config) # Instantiate CacheManager
        self._exchange_service = None # Initialize exchange service attribute

        # Data processor
        self._data_processor = DataProcessor(
            hass,
            area,
            currency,
            config,
            self._tz_service, # Pass the instantiated service
            self # Pass self to DataProcessor, it will get exchange_service later
        )
        # Store rate limiter context information instead of creating an instance
        # Rate limiting is now handled by a simple lock and timestamp check
        # self._rate_limiter_context = f\"unified_price_manager_{area}\"

        # API request tracking
        self._last_api_fetch = None
        self._next_scheduled_fetch = None
        # self._last_data = None # Replaced with CacheManager
        self._consecutive_failures = 0

        # Display settings - explicitly ensure display_unit is set from config with strong default
        # This is crucial for proper operation with selected display units
        if Config.DISPLAY_UNIT in config:
            self.display_unit = config[Config.DISPLAY_UNIT]
            _LOGGER.debug(f"Using explicitly configured display_unit from config: {self.display_unit}")
        else:
            self.display_unit = Defaults.DISPLAY_UNIT
            _LOGGER.warning(f"No display_unit in config for {area}, using default: {self.display_unit}")

        # Set use_subunit based on display_unit - crucial for proper unit conversion
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
        _LOGGER.debug(f"UnifiedPriceManager initialized for {area} with display_unit={self.display_unit}, use_subunit={self.use_subunit}")

        self.vat_rate = config.get(Config.VAT, Defaults.VAT_RATE) / 100  # Convert from percentage to rate
        self.include_vat = config.get(Config.INCLUDE_VAT, Defaults.INCLUDE_VAT)

        # Configure source priorities and API class mappings
        self._configure_sources()

    def _configure_sources(self):
        """Configure source priorities and API class mappings."""
        # Filter source_priority to only include supported sources for this area
        self._source_priority = [s for s in self._source_priority if s in self._supported_sources]

        # If no sources remain after filtering, use all supported sources for this area
        if not self._source_priority:
            _LOGGER.warning(
                "No configured sources are supported for area %s. Using all supported sources: %s",
                self.area,
                self._supported_sources
            )
            self._source_priority = self._supported_sources
        elif not self._source_priority:
             _LOGGER.error("No sources configured or supported for area %s.", self.area)


        # Map source names to their API classes
        self._source_api_map = {
            Source.NORDPOOL: NordpoolAPI, # Changed from NordpoolAdapter
            Source.ENTSOE: EntsoeAPI,       # Changed from EntsoeAdapter
            Source.AEMO: AemoAPI,         # Changed from AemoAdapter
            Source.EPEX: EpexAPI,         # Changed from EpexAdapter
            Source.ENERGI_DATA_SERVICE: EnergiDataAdapter, # Remains Adapter
            Source.AMBER: AmberAdapter, # Remains Adapter
            Source.COMED: ComedAdapter, # Remains Adapter
            Source.OMIE: OmieAPI,         # Changed from OmieAdapter
            Source.STROMLIGNING: StromligningAPI, # Changed from StromligningAdapter
            # Add other API classes here
        }

        # Build ordered list of API classes based on priority
        self._api_classes = []
        for source in self._source_priority:
            if source in self._source_api_map:
                self._api_classes.append(self._source_api_map[source])
            else:
                _LOGGER.warning("Source '%s' configured but no matching API class found.", source)

        _LOGGER.info(f"Configured sources for area {self.area}: {[cls.__name__ for cls in self._api_classes]}")

    async def _ensure_exchange_service(self):
        """Ensure the exchange service is initialized."""
        if self._exchange_service is None:
            # Use the singleton helper to get/create the service
            self._exchange_service = await get_exchange_service(session=async_get_clientsession(self.hass))
            # Pass the initialized service to the data processor if it expects it
            # Assuming DataProcessor needs the actual service instance:
            if hasattr(self._data_processor, '_exchange_service'):
                 self._data_processor._exchange_service = self._exchange_service
            else:
                 _LOGGER.warning("DataProcessor does not have _exchange_service attribute to set.")


    async def fetch_data(self, force: bool = False) -> Dict[str, Any]:
        """Fetch price data considering rate limits and caching.

        Args:
            force: Whether to force fetch even if rate limited

        Returns:
            Dictionary with processed data
        """
        now = dt_util.now()
        today_date = now.date() # Get today's date
        area_key = self.area # Key for rate limiting

        # Ensure exchange service is initialized before fetching/processing
        await self._ensure_exchange_service()

        # --- Decision to Fetch (incorporating FetchDecisionMaker) ---
        # Get current cache status to inform fetch decision
        cached_data_for_decision = self._cache_manager.get_data(
            area=self.area,
            target_date=today_date,
            max_age_minutes=Defaults.CACHE_TTL
        )

        has_current_hour_price_in_cache = False
        has_complete_data_for_today_in_cache = False

        if cached_data_for_decision:
            # Directly inspect the already processed cached_data_for_decision
            # The cache stores fully processed data, so we don't need to re-process it here.
            if cached_data_for_decision.get("current_price") is not None:
                has_current_hour_price_in_cache = True
            if cached_data_for_decision.get("statistics", {}).get("complete_data", False):
                has_complete_data_for_today_in_cache = True
            
            _LOGGER.debug(
                f"[{self.area}] Decision making: cached_data_for_decision found. "
                f"Current price available in cache: {has_current_hour_price_in_cache}. "
                f"Complete data in cache (20+ hrs): {has_complete_data_for_today_in_cache}. "
                f"Cached stats content: {cached_data_for_decision.get('statistics')}"
            )
        else:
            _LOGGER.debug(f"[{self.area}] Decision making: no cached_data_for_decision found.")

        # Instantiate FetchDecisionMaker
        from .fetch_decision import FetchDecisionMaker # Local import
        decision_maker = FetchDecisionMaker(tz_service=self._tz_service)

        # Get last fetch time from the shared dictionary for this area
        last_fetch_for_decision = _LAST_FETCH_TIME.get(area_key)

        should_fetch_from_api, fetch_reason = decision_maker.should_fetch(
            now=now,
            last_fetch=last_fetch_for_decision,
            fetch_interval=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES, # Use the same interval as rate limiter
            has_current_hour_price=has_current_hour_price_in_cache,
            has_complete_data_for_today=has_complete_data_for_today_in_cache
        )

        if not force and not should_fetch_from_api:
            _LOGGER.info(f"Skipping API fetch for area {self.area} based on FetchDecisionMaker: {fetch_reason}")
            if cached_data_for_decision:
                _LOGGER.debug("Returning data based on initial cache check for decision making for %s", self.area)
                # Ensure the cached data is marked correctly if it's used
                cached_data_for_decision["using_cached_data"] = True
                # Re-process if it wasn't fully processed or to update timestamps
                return await self._process_result(cached_data_for_decision, is_cached=True)
            else:
                _LOGGER.warning(
                    f"FetchDecisionMaker advised against fetching for {self.area}, but no cached data was available for decision. "
                    f"This might indicate an issue or an edge case (e.g. initial startup with no cache yet)."
                )
                # Attempt to generate an empty result, or consider if a fetch should be forced here
                return await self._generate_empty_result(error=f"Fetch skipped by decision maker, no cache: {fetch_reason}")

        # --- Rate Limiting Lock (moved after initial fetch decision) ---
        # If we decided to fetch (or force is true), then acquire the lock.
        async with _FETCH_LOCK: # Use asyncio Lock for atomicity
            # Re-check last_fetch inside the lock to ensure atomicity for rate limiting
            last_fetch_for_rate_limit = _LAST_FETCH_TIME.get(area_key)
            min_interval = timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES)

            if not force and last_fetch_for_rate_limit:
                time_since_last_fetch = now - last_fetch_for_rate_limit
                if time_since_last_fetch < min_interval:
                    next_fetch_allowed_in_seconds = (min_interval - time_since_last_fetch).total_seconds()
                    _LOGGER.info(
                        f"Rate limiting in effect for area {self.area} (checked after fetch decision). "
                        f"Next fetch allowed in {next_fetch_allowed_in_seconds:.1f} seconds. "
                        f"Using cached data if available."
                    )
                    # Use cached data if rate limited - specify today's date
                    # This is the same logic as before, but now it's after the FetchDecisionMaker check
                    # and inside the rate limiting lock.
                    cached_data_rate_limited = self._cache_manager.get_data(
                        area=self.area,
                        target_date=today_date,
                        max_age_minutes=Defaults.CACHE_TTL
                    )
                    if cached_data_rate_limited:
                        _LOGGER.debug("Returning rate-limited cached data for %s (after decision check)", self.area)
                        cached_data_rate_limited["using_cached_data"] = True
                        cached_data_rate_limited["next_fetch_allowed_in_seconds"] = round(next_fetch_allowed_in_seconds, 1)
                        return await self._process_result(cached_data_rate_limited, is_cached=True)
                    else:
                        _LOGGER.warning("Rate limited for %s (after decision check), but no cached data available for today (%s).", self.area, today_date)
                        return await self._generate_empty_result(error="Rate limited (after decision), no cache available")

            # If not rate limited or forced, proceed to fetch. Update fetch timestamp.
            _LOGGER.info(f"Proceeding with API fetch for area {self.area} (Reason: {fetch_reason}, Force: {force})")
            _LAST_FETCH_TIME[area_key] = now # Update fetch time now that we are committed to fetching

        # --- Actual Fetching Logic (outside the rate limiting lock, but after decision and timestamp update) ---

        # Fetch data using the new FallbackManager
        try:
            # Prepare API instances - pass necessary context
            # Ensure session is created correctly
            session = async_get_clientsession(self.hass)
            api_instances = [
                cls(
                    config=self.config,
                    session=session,
                    timezone_service=self._tz_service,
                    # Pass other context if needed by base class or specific APIs
                    # hass=self.hass, # Example if HASS instance is needed
                ) for cls in self._api_classes
            ]

            if not api_instances:
                _LOGGER.error(f"No API sources available/configured for area {self.area}")
                self._consecutive_failures += 1
                # Try cache before giving up - specify today's date
                cached_data = self._cache_manager.get_data(
                    area=self.area,
                    target_date=today_date, # Specify today
                    max_age_minutes=Defaults.CACHE_TTL
                )
                if cached_data:
                    _LOGGER.warning("No APIs available for %s, using cached data.", self.area)
                    cached_data["using_cached_data"] = True
                    processed_cached_data = await self._process_result(cached_data, is_cached=True)
                    processed_cached_data["using_cached_data"] = True # Ensure flag is set
                    return processed_cached_data
                return await self._generate_empty_result(error="No API sources configured")

            # Fetch with fallback using the new manager
            result = await self._fallback_manager.fetch_with_fallbacks(
                apis=api_instances,
                area=self.area,
                currency=self.currency, # Pass target currency (conversion handled later)
                reference_time=now,
                hass=self.hass, # Pass hass if needed by APIs
                session=session, # Pass session
            )

            # --- DEBUG LOGGING START ---
            if result:
                _LOGGER.debug(f"[{self.area}] Result from FallbackManager: Keys={list(result.keys())}, ErrorKeyPresent={result.get('error') is not None}")
                # Log the raw data content if small enough or relevant parts
                raw_content_preview = str(result.get('xml_responses') or result.get('dict_response'))[:200] # Check both possible raw data keys
                _LOGGER.debug(f"[{self.area}] Raw data preview: {raw_content_preview}...")
            else:
                _LOGGER.debug(f"[{self.area}] Result from FallbackManager is None or empty.")
            # --- DEBUG LOGGING END ---

            # Check if FallbackManager returned a result dictionary AND it doesn't contain the 'error' key added by FallbackManager on total failure.
            if isinstance(result, dict) and "error" not in result:
                _LOGGER.info(f"[{self.area}] Successfully received raw data structure from FallbackManager. Source: {result.get('data_source', 'unknown')}")

                # Process the raw result (this is where parsing happens)
                processed_data = await self._process_result(result)

                # NOW check if processing yielded hourly_prices data and has_data flag is true
                if processed_data and processed_data.get("has_data") and processed_data.get("hourly_prices"): # Check for hourly_prices *after* processing
                    _LOGGER.info(f"[{self.area}] Successfully processed data, found 'hourly_prices'.")
                    self._consecutive_failures = 0
                    self._active_source = processed_data.get("data_source", "unknown") # Use source from processed data
                    self._attempted_sources = processed_data.get("attempted_sources", [])
                    self._fallback_sources = [s for s in self._attempted_sources if s != self._active_source]
                    self._using_cached_data = False
                    processed_data["using_cached_data"] = False

                    # Cache the successfully processed data
                    self._cache_manager.store(
                        data=processed_data,
                        area=self.area,
                        source=processed_data.get("data_source", "unknown"),
                        timestamp=now
                    )
                    return processed_data
                else:
                    # Processing failed to produce hourly_raw or marked as no data
                    error_info = processed_data.get("error", "Processing failed to produce valid data") if processed_data else "Processing returned None or empty"
                    _LOGGER.error(f"[{self.area}] Failed to process fetched data. Error: {error_info}")
                    # Fall through to failure handling (try cache)

            # Handle fetch failure (result is None or the error dict from FallbackManager) OR processing failure
            error_info = "Unknown fetch/processing error" # Default error
            if result and "error" in result and isinstance(result.get("error"), Exception): # Check if error key exists and is an Exception
                 error_info = str(result.get("error", "Unknown fetch error")) # Error from FallbackManager
            elif not result:
                 error_info = "No result from FallbackManager"
            # If processing failed, error_info might have been set in the 'else' block above

            _LOGGER.error(f"Failed to get valid processed data for area {self.area}. Error: {error_info}")
            self._consecutive_failures += 1
            self._attempted_sources = result.get("attempted_sources", []) if result else []
            self._active_source = "None"
            self._fallback_sources = self._attempted_sources # All attempted sources failed or processing failed

            # Try to use cached data as a last resort - specify today's date
            cached_data = self._cache_manager.get_data(
                area=self.area,
                target_date=today_date, # Specify today
                max_age_minutes=Defaults.CACHE_TTL
            )
            if cached_data:
                _LOGGER.warning("Using cached data for %s due to fetch/processing failure.", self.area)
                self._using_cached_data = True
                cached_data["using_cached_data"] = True # Mark as cached
                # Re-process cached data
                processed_cached_data = await self._process_result(cached_data, is_cached=True)
                processed_cached_data["using_cached_data"] = True # Ensure flag is set
                return processed_cached_data
            else:
                _LOGGER.error("All sources/processing failed for %s and no usable cache available for today (%s).", self.area, today_date)
                self._using_cached_data = True # Indicate we intended to use cache but failed
                # Generate empty result if fetch and cache fail
                return await self._generate_empty_result(error=f"Fetch/Processing failed: {error_info}")

        except Exception as e:
            _LOGGER.error(f"Unexpected error during fetch_data for area {self.area}: {e}", exc_info=True)
            self._consecutive_failures += 1

            # Ensure exchange service is initialized even on error path for _generate_empty_result
            await self._ensure_exchange_service()

            # Try cache on unexpected error - specify today's date
            cached_data = self._cache_manager.get_data(
                area=self.area,
                target_date=today_date, # Specify today
                max_age_minutes=Defaults.CACHE_TTL
            )
            if cached_data:
                 _LOGGER.warning("Using cached data for %s due to unexpected error: %s", self.area, e)
                 self._using_cached_data = True
                 cached_data["using_cached_data"] = True
                 processed_cached_data = await self._process_result(cached_data, is_cached=True)
                 processed_cached_data["using_cached_data"] = True # Ensure flag is set
                 return processed_cached_data
            else:
                 # Generate empty result if no cache
                 return await self._generate_empty_result(error=f"Unexpected error: {str(e)}")


    async def _process_result(self, result: Dict[str, Any], is_cached: bool = False) -> Dict[str, Any]:
        """Process raw result data (either fresh or cached).

        Args:
            result: Raw result data from fetch or cache.
            is_cached: Flag indicating if the data came from cache.

        Returns:
            Processed data dictionary.
        """
        # Ensure exchange service is initialized before processing
        await self._ensure_exchange_service()

        # Basic validation
        if not result or not isinstance(result, dict):
            _LOGGER.error(f"Invalid result provided for processing area {self.area}")
            return await self._generate_empty_result(error="Invalid data structure for processing")

        # Add/update metadata before processing
        result["area"] = self.area
        result["target_currency"] = self.currency
        # Set using_cached_data based on the flag passed, not just the input dict
        result["using_cached_data"] = is_cached
        result["vat_rate"] = self.vat_rate * 100
        result["include_vat"] = self.include_vat
        result["display_unit"] = self.display_unit

        # Use data processor to generate final result
        try:
            processed_data = await self._data_processor.process(result)
            processed_data["has_data"] = bool(processed_data.get("hourly_prices")) # Add a simple flag
            processed_data["last_update"] = dt_util.now().isoformat() # Timestamp the processing time

            # Get source info directly from the input result dictionary
            attempted_sources = result.get("attempted_sources", [])
            active_source = result.get("data_source", "unknown") # Source determined by FallbackManager or cache
            fallback_sources = [s for s in attempted_sources if s != active_source]

            # Ensure fallback/attempt info is preserved using data from the result
            processed_data["attempted_sources"] = attempted_sources
            processed_data["fallback_sources"] = fallback_sources
            processed_data["data_source"] = active_source # Reflect the source determined during fetch/cache retrieval

            # Ensure the final flag reflects the input is_cached status
            processed_data["using_cached_data"] = is_cached

            return processed_data
        except Exception as proc_err:
            _LOGGER.error(f"Error processing data for area {self.area}: {proc_err}", exc_info=True)
            return await self._generate_empty_result(error=f"Processing error: {proc_err}")


    async def _generate_empty_result(self, error: Optional[str] = None) -> Dict[str, Any]:
        """Generate an empty result when data is unavailable.

        Args:
            error: Optional error message to include.

        Returns:
            Empty result dictionary with standard structure.
        """
        # Ensure exchange service is initialized before processing empty result
        await self._ensure_exchange_service()

        now = dt_util.now()

        # Create complete empty data structure without calling _process_result again
        empty_data = {
            "source": "None",
            "area": self.area,
            "currency": self.currency,
            "target_currency": self.currency,
            "hourly_prices": {},
            "raw_data": None,
            "source_timezone": None,
            "attempted_sources": self._attempted_sources,
            "fallback_sources": self._fallback_sources,
            "using_cached_data": self._using_cached_data or (error == "Rate limited, no cache available"),
            "consecutive_failures": self._consecutive_failures,
            "last_fetch_attempt": _LAST_FETCH_TIME.get(self.area, now).isoformat() if _LAST_FETCH_TIME.get(self.area) else now.isoformat(),
            "error": error or f"Failed to fetch data after {self._consecutive_failures} attempts",
            "has_data": False,
            "last_update": now.isoformat(),
            "vat_rate": self.vat_rate * 100,
            "include_vat": self.include_vat,
            "display_unit": self.display_unit,
            "current_price": None,
            "average_price": None,
            "min_price": None,
            "max_price": None,
            "off_peak_1": None,
            "peak": None,
            "off_peak_2": None,
            "weighted_average_price": None,
            "data_source": "None",
            "price_in_cents": False
        }

        # Directly return the structured empty data without processing
        return empty_data

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the data cache.

        Returns:
            Cache statistics from CacheManager.
        """
        # Delegate to CacheManager
        return self._cache_manager.get_cache_stats()

    async def clear_cache(self, target_date: Optional[date] = None):
        """Clear the price cache via the manager, optionally for a specific date, and force a fresh fetch."""
        # Cache manager's clear_cache returns a bool, don't await it
        cleared = self._cache_manager.clear_cache(target_date=target_date)
        if cleared:
            _LOGGER.info("Cache cleared for area %s. Forcing fresh fetch.", self.area)
            # We need to force a new fetch
            await self.fetch_data(force=True)
        return cleared

    async def async_close(self):
        """Close any open sessions and resources."""
        # Close the exchange service session if it was initialized
        if self._exchange_service:
            await self._exchange_service.close()
        # Note: aiohttp session passed to APIs is managed by HA and shouldn't be closed here.


# --- Coordinator Class ---

class UnifiedPriceCoordinator(DataUpdateCoordinator):
    """Data update coordinator using the unified price manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        update_interval: timedelta,
        config: Dict[str, Any],
    ):
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            update_interval: Update interval
            config: Configuration dictionary
        """
        # Ensure minimum update interval from constants is respected
        min_interval_seconds = Defaults.UPDATE_INTERVAL * 60 # Default interval in minutes
        effective_interval_seconds = max(update_interval.total_seconds(), min_interval_seconds)
        effective_update_interval = timedelta(seconds=effective_interval_seconds)

        if update_interval.total_seconds() < min_interval_seconds:
             _LOGGER.warning(
                 "Configured update interval (%s s) is less than the minimum allowed (%s s). Using minimum interval.",
                 update_interval.total_seconds(),
                 min_interval_seconds
             )


        super().__init__(
            hass,
            _LOGGER,
            name=f"gespot_{area}", # Removed backslash
            update_interval=effective_update_interval, # Use effective interval
        )

        self.area = area
        self.currency = currency
        self.config = config

        # Create unified price manager
        self.price_manager = UnifiedPriceManager(
            hass=hass,
            area=area,
            currency=currency,
            config=config
        )

    async def _async_update_data(self):
        """Fetch data from price manager."""
        try:
            # Fetch data using the manager's logic (includes rate limiting, fallback, caching)
            data = await self.price_manager.fetch_data()
            # Manager always returns a dict; check 'has_data' flag or 'error' key for success
            if not data.get("has_data"):
                 # Log specific error if available
                 error_msg = data.get("error", "No data returned from price manager or data marked as invalid")
                 _LOGGER.warning("Update failed for area %s: %s", self.area, error_msg)
                 # Return the empty/error data structure from the manager
                 return data
            # Data is valid
            return data
        except Exception as e:
            _LOGGER.error("Unexpected error during coordinator update for area %s: %s", self.area, e, exc_info=True)
            # Return last known good data if available
            if self.data:
                _LOGGER.warning("Returning last known data for %s due to update error.", self.area)
                return self.data
            else:
                # If no previous data, return an empty structure consistent with manager's output
                # Use try-except in case manager itself fails during error generation
                try:
                    return await self.price_manager._generate_empty_result(error=f"Coordinator update error: {e}")
                except Exception as gen_err:
                    _LOGGER.error("Failed to generate empty result during coordinator error handling: %s", gen_err)
                    # Return a minimal dict if empty result generation fails
                    return {"error": f"Coordinator update error and failed to generate empty result: {e}", "has_data": False}

    async def force_update(self):
        """Force an update regardless of schedule and rate limits."""
        _LOGGER.info(f"Forcing update for area {self.area}")
        # Call manager's fetch with force=True
        await self.price_manager.fetch_data(force=True)
        # Trigger HA state update
        await self.async_request_refresh()
        _LOGGER.debug(f"Force update complete for area {self.area}")


    async def clear_cache(self, target_date: Optional[date] = None):
        """Clear the price cache via the manager, optionally for a specific date, and force a fresh fetch."""
        # Call the manager's clear_cache method with await since it's an async method
        cleared = await self.price_manager.clear_cache(target_date=target_date)
        if cleared:
            _LOGGER.info("Cache cleared for area %s. Forcing fresh fetch.", self.area)
            await self.force_update()  # This will call fetch_data(force=True)
        return cleared

    async def async_close(self):
        """Close any open sessions and resources via the manager."""
        await self.price_manager.async_close()
        _LOGGER.debug("Closed resources for coordinator %s", self.area)

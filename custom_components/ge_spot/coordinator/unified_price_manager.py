"""Unified Price Manager for ge-spot integration."""
import logging
from datetime import timedelta, datetime, time
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
from ..api.nordpool import NordpoolAPI
from ..api.entsoe import EntsoeAPI
from ..api.aemo import AemoAPI
from ..api.epex import EpexAPI
from ..api.energi_data import EnergiDataAPI
from ..api.amber import AmberAPI
from ..api.comed import ComedAPI
from ..api.omie import OmieAPI
from ..api.stromligning import StromligningAPI


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
        self._tz_service = TimezoneService(hass) # Instantiate TimezoneService
        self._fallback_manager = FallbackManager()
        self._cache_manager = CacheManager(hass=hass, config=config) # Instantiate CacheManager

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
        # self._last_data = None # Replaced by CacheManager
        self._consecutive_failures = 0

        # Display settings
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
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
            Source.NORDPOOL: NordpoolAPI,
            Source.ENTSOE: EntsoeAPI,
            Source.AEMO: AemoAPI,
            Source.EPEX: EpexAPI,
            Source.ENERGI_DATA_SERVICE: EnergiDataAPI,
            Source.AMBER: AmberAPI,
            Source.COMED: ComedAPI,
            Source.OMIE: OmieAPI,
            Source.STROMLIGNING: StromligningAPI,
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
        area_key = self.area # Key for rate limiting

        # Ensure exchange service is initialized before fetching/processing
        await self._ensure_exchange_service()

        # --- Rate Limiting Start ---
        async with _FETCH_LOCK: # Use asyncio Lock for atomicity
            last_fetch = _LAST_FETCH_TIME.get(area_key)
            min_interval = timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES)

            if not force and last_fetch:
                time_since_last_fetch = now - last_fetch
                if time_since_last_fetch < min_interval:
                    _LOGGER.info(
                        f"Rate limiting in effect for area {self.area}. "
                        f"Next fetch allowed in {(min_interval - time_since_last_fetch).total_seconds():.1f} seconds. "
                        f"Using cached data if available."
                    )
                    # Use cached data if rate limited
                    cached_data = self._cache_manager.get_cached_data() # Removed max_age here, CacheManager handles TTL internally
                    if cached_data:
                        _LOGGER.debug("Returning rate-limited cached data for %s", self.area)
                        # Ensure the cached data is marked correctly before processing
                        cached_data["using_cached_data"] = True
                        # Re-process to ensure stats etc. are up-to-date relative to 'now'
                        processed_cached_data = await self._process_result(cached_data, is_cached=True)
                        # Explicitly set the flag again after processing, as _process_result might reset it based on input
                        processed_cached_data["using_cached_data"] = True
                        return processed_cached_data
                    else:
                        _LOGGER.warning("Rate limited for %s, but no cached data available.", self.area)
                        # Generate empty result if no cache and rate limited
                        # Pass the specific rate limit error message
                        return await self._generate_empty_result(error="Rate limited, no cache available")

            # If not rate limited or forced, proceed to fetch
            _LOGGER.info(f"Fetching price data for area {self.area}")
            # Update fetch timestamp *before* the actual fetch to prevent race conditions
            _LAST_FETCH_TIME[area_key] = now
        # --- Rate Limiting End ---


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
                # Try cache before giving up - Use CACHE_TTL for max age
                cached_data = self._cache_manager.get_cached_data(max_age_minutes=Defaults.CACHE_TTL)
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

            # Check if fetch was successful
            if result and result.get("hourly_prices") and not result.get("error"):
                _LOGGER.info(f"Successfully fetched data for area {self.area} via FallbackManager.")
                self._consecutive_failures = 0
                self._active_source = result.get("data_source", "unknown")
                self._attempted_sources = result.get("attempted_sources", [])
                # Determine fallback sources (attempted minus the successful one)
                self._fallback_sources = [s for s in self._attempted_sources if s != self._active_source]
                self._using_cached_data = False # Fresh data fetched
                result["using_cached_data"] = False # Ensure flag is set correctly

                # Process the successful result
                processed_data = await self._process_result(result)

                # Cache the successfully processed data
                self._cache_manager.update_cache(processed_data)

                return processed_data

            else:
                # Handle fetch failure from all sources
                error_info = result.get("error", "Unknown fetch error") if result else "No result from FallbackManager"
                _LOGGER.error(f"Failed to fetch data for area {self.area} from all sources. Error: {error_info}")
                self._consecutive_failures += 1
                self._attempted_sources = result.get("attempted_sources", []) if result else []
                self._active_source = "None"
                self._fallback_sources = self._attempted_sources # All attempted sources failed

                # Try to use cached data as a last resort - Use CACHE_TTL for max age
                cached_data = self._cache_manager.get_cached_data(max_age_minutes=Defaults.CACHE_TTL)
                if cached_data:
                    _LOGGER.warning("Using cached data for %s due to fetch failure.", self.area)
                    self._using_cached_data = True
                    cached_data["using_cached_data"] = True # Mark as cached
                    # Re-process cached data
                    processed_cached_data = await self._process_result(cached_data, is_cached=True)
                    processed_cached_data["using_cached_data"] = True # Ensure flag is set
                    return processed_cached_data
                else:
                    _LOGGER.error("All sources failed for %s and no usable cache available.", self.area)
                    self._using_cached_data = True # Indicate we intended to use cache but failed
                    # Generate empty result if fetch and cache fail
                    return await self._generate_empty_result(error=f"All sources failed: {error_info}")


        except Exception as e:
            _LOGGER.error(f"Unexpected error during fetch_data for area {self.area}: {e}", exc_info=True)
            self._consecutive_failures += 1

            # Ensure exchange service is initialized even on error path for _generate_empty_result
            await self._ensure_exchange_service()

            # Try cache on unexpected error - Use CACHE_TTL for max age
            cached_data = self._cache_manager.get_cached_data(max_age_minutes=Defaults.CACHE_TTL)
            if cached_data:
                 _LOGGER.warning("Using cached data for %s due to unexpected error: %s", self.area, e)
                 self._using_cached_data = True
                 cached_data["using_cached_data"] = True
                 processed_cached_data = await self._process_result(cached_data, is_cached=True)
                 processed_cached_data["using_cached_data"] = True # Ensure flag is set
                 return processed_cached_data
            else:
                 # Use last known data if available, otherwise return empty result
                 # if self._last_data: # Replaced by cache check
                 #     return self._last_data
                 # else:
                 return await self._generate_empty_result(error=f"Unexpected error: {e}")


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
            # Ensure fallback/attempt info is preserved
            processed_data["attempted_sources"] = self._attempted_sources
            processed_data["fallback_sources"] = self._fallback_sources
            processed_data["data_source"] = self._active_source # Reflect the source determined during fetch
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
            Empty result dictionary, processed to have standard structure.
        """
        # Ensure exchange service is initialized before processing empty result
        await self._ensure_exchange_service()

        now = dt_util.now()

        # Create base empty data structure
        empty_data = {
            "source": "None",
            "area": self.area,
            "currency": self.currency, # Use target currency
            "hourly_prices": {},
            "raw_data": None, # No raw data available
            "api_timezone": None, # Unknown timezone
            # Include metadata about the failure state
            "attempted_sources": self._attempted_sources,
            "fallback_sources": self._fallback_sources, # All attempted if failed
            # Reflects if cache was *intended* or if this is due to rate limit w/o cache
            "using_cached_data": self._using_cached_data or (error == "Rate limited, no cache available"),
            "consecutive_failures": self._consecutive_failures,
            "last_fetch_attempt": _LAST_FETCH_TIME.get(self.area, now).isoformat() if _LAST_FETCH_TIME.get(self.area) else now.isoformat(),
            "error": error or f"Failed to fetch data after {self._consecutive_failures} attempts"
        }

        # Process this empty structure
        # Pass the correct cache status based on the error or internal state
        is_cached_status = self._using_cached_data or (error == "Rate limited, no cache available")
        processed_empty = await self._process_result(empty_data, is_cached=is_cached_status)
        processed_empty["has_data"] = False # Explicitly mark as no data
        processed_empty["last_update"] = now.isoformat() # Timestamp the failure time

        return processed_empty


    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the data cache.

        Returns:
            Cache statistics from CacheManager.
        """
        # Delegate to CacheManager
        return self._cache_manager.get_cache_stats()

    async def clear_cache(self) -> bool:
        """Clear the data cache.

        Returns:
            True if cache was cleared.
        """
        # Delegate to CacheManager
        self._cache_manager.clear_cache()
        _LOGGER.info("Cleared cache for area %s", self.area)
        return True

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


    async def clear_cache(self):
        """Clear the price cache via the manager."""
        cleared = await self.price_manager.clear_cache()
        if cleared:
            _LOGGER.info("Cache cleared for area %s via coordinator.", self.area)
            # Optionally trigger a refresh after clearing cache
            # await self.async_request_refresh()
        return cleared

    async def async_close(self):
        """Close any open sessions and resources via the manager."""
        await self.price_manager.async_close()
        _LOGGER.debug("Closed resources for coordinator %s", self.area)

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
from ..const.time import ValidationRetry
from ..api import get_sources_for_region
from ..api.base.base_price_api import BasePriceAPI
from ..api.base.data_structure import StandardizedPriceData, create_standardized_price_data
from ..api.base.session_manager import close_session
from ..timezone.service import TimezoneService # Added import
from ..utils.exchange_service import ExchangeRateService, get_exchange_service
from .data_processor import DataProcessor
from .fallback_manager import FallbackManager # Import the new FallbackManager
from .cache_manager import CacheManager # Import CacheManager

# Import all API implementations here to have them available
from ..api.nordpool import NordpoolAPI
from ..api.entsoe import EntsoeAPI
from ..api.aemo import AemoAPI
from ..api.energy_charts import EnergyChartsAPI
from ..api.energi_data import EnergiDataAPI
from ..api.amber import AmberAPI
from ..api.comed import ComedAPI
from ..api.omie import OmieAPI
from ..api.stromligning import StromligningAPI


_LOGGER = logging.getLogger(__name__)

# Validation result constants for clarity
AUTH_ERROR = True      # Validation failed due to authentication (no retry)
NOT_AUTH_ERROR = False # Validation failed for other reasons (will retry)

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
        self._coordinator_created_at = dt_util.utcnow()  # Track when coordinator was created for better rate limit messaging

        # Debug: Log config keys to diagnose API key issue
        _LOGGER.debug(
            f"UnifiedPriceManager init for {area}: config keys={list(config.keys())}, "
            f"api_key={'PRESENT' if config.get(Config.API_KEY) or config.get('api_key') else 'MISSING'}"
        )

        self.timezone_service = TimezoneService(
            hass=hass,
            area=area,
            config=config
        )

        # API sources and tracking
        self._supported_sources = get_sources_for_region(area)
        self._source_priority = config.get(Config.SOURCE_PRIORITY, Source.DEFAULT_PRIORITY)
        self._active_source = None
        self._attempted_sources = []
        self._fallback_sources = [] # Keep track of sources used as fallback
        self._using_cached_data = False

        # Track failed sources for implicit validation
        # Dict[str, datetime] - Maps source name to last failure time (None = never failed or succeeded after failure)
        self._failed_sources = {}
        # Set[str] - Sources with scheduled daily retry tasks
        self._retry_scheduled = set()

        # Services and utilities
        self._tz_service = TimezoneService(hass=hass, area=area, config=config) # Initialize with all parameters
        self._fallback_manager = FallbackManager()
        self._cache_manager = CacheManager(hass=hass, config=config) # Instantiate CacheManager
        self._exchange_service: ExchangeRateService | None = None # Initialize exchange service attribute

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
            Source.NORDPOOL: NordpoolAPI,
            Source.ENTSOE: EntsoeAPI,
            Source.AEMO: AemoAPI,
            Source.ENERGY_CHARTS: EnergyChartsAPI,
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

        # Log configured sources using source_type instead of class names
        configured_source_names = [
            cls(config={}).source_type for cls in self._api_classes
        ]
        _LOGGER.info(f"Configured sources for area {self.area}: {configured_source_names}")

    def get_validated_sources(self) -> List[str]:
        """Get list of validated source names (sources that succeeded at least once)."""
        return sorted([
            src for src, last_fail in self._failed_sources.items()
            if last_fail is None  # None = never failed OR succeeded after last failure
        ])

    def get_disabled_sources(self) -> List[str]:
        """Get list of disabled source names (sources that failed recently)."""
        return sorted([
            src for src, last_fail in self._failed_sources.items()
            if last_fail is not None
        ])

    def get_enabled_sources(self) -> List[str]:
        """Get list of currently enabled source names."""
        all_sources = [cls(config={}).source_type for cls in self._api_classes]
        disabled = self.get_disabled_sources()
        return sorted([s for s in all_sources if s not in disabled])

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

    async def _schedule_daily_retry(self, source_name: str, api_class: Type[BasePriceAPI]):
        """Schedule daily retry for a failed source during special hours.

        Retries once per day during configured windows (e.g., 13:00-15:00).
        Uses same exponential backoff as normal fetch via FallbackManager.

        Args:
            source_name: Name of the source to retry
            api_class: API class to retry
        """
        import random

        last_retry = None

        while True:
            now = dt_util.now()
            current_hour = now.hour
            today_date = now.date()

            # Check if we're in a special hour window
            in_special_hours = any(
                start <= current_hour < end
                for start, end in Network.Defaults.SPECIAL_HOUR_WINDOWS
            )

            # Only retry once per day
            should_retry = (
                in_special_hours and
                (last_retry is None or last_retry.date() < today_date)
            )

            if should_retry:
                # Random delay within current hour to spread load
                from ..const.time import ValidationRetry
                delay_seconds = random.randint(0, ValidationRetry.MAX_RANDOM_DELAY_SECONDS)
                _LOGGER.info(
                    f"[{self.area}] Daily retry for '{source_name}' in {delay_seconds}s"
                )
                await asyncio.sleep(delay_seconds)

                # Trigger a forced fetch (will try this source again)
                try:
                    result = await self.fetch_data(force=True)

                    # Check if this specific source succeeded
                    if result and result.get("data_source") == source_name:
                        _LOGGER.info(
                            f"[{self.area}] ✓ '{source_name}' daily retry successful - "
                            f"source re-enabled"
                        )
                        self._retry_scheduled.discard(source_name)
                        return  # Success, stop retrying
                    else:
                        _LOGGER.debug(
                            f"[{self.area}] '{source_name}' daily retry failed, "
                            f"will try again tomorrow"
                        )

                except Exception as e:
                    _LOGGER.warning(
                        f"[{self.area}] Error during '{source_name}' daily retry: {e}"
                    )

                last_retry = now

            # Sleep until next check (1 hour)
            await asyncio.sleep(3600)

    async def fetch_data(self, force: bool = False) -> Dict[str, Any]:
        """Fetch price data with implicit source validation.

        Sources are validated implicitly during fetch:
        - Success → Source marked as working (failure timestamp cleared)
        - Failure → Source marked as failed, skipped for 24 hours, daily retry scheduled

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

        # --- Decision to Fetch (using DataValidity) ---
        # Get current cache status to inform fetch decision
        cached_data_for_decision = self._cache_manager.get_data(
            area=self.area,
            target_date=today_date
        )

        # Extract data validity from cache if available
        from .data_validity import DataValidity
        data_validity = DataValidity()  # Default: no valid data

        if cached_data_for_decision:
            # Extract DataValidity from cached data
            if "data_validity" in cached_data_for_decision:
                try:
                    data_validity = DataValidity.from_dict(cached_data_for_decision["data_validity"])
                    _LOGGER.debug(f"[{self.area}] Loaded data validity from cache: {data_validity}")
                except Exception as e:
                    _LOGGER.warning(f"[{self.area}] Failed to load data validity from cache: {e}")
            else:
                # Fallback: calculate validity from cached price data
                try:
                    from .data_validity import calculate_data_validity
                    current_interval_key = self._tz_service.get_current_interval_key()
                    # Cached interval keys are in target_timezone
                    target_timezone = str(self._tz_service.target_timezone)
                    data_validity = calculate_data_validity(
                        interval_prices=cached_data_for_decision.get("interval_prices", {}),
                        tomorrow_interval_prices=cached_data_for_decision.get("tomorrow_interval_prices", {}),
                        now=now,
                        current_interval_key=current_interval_key,
                        target_timezone=target_timezone  # Keys are in this timezone
                    )
                    _LOGGER.debug(f"[{self.area}] Calculated data validity from cache: {data_validity}")
                except Exception as e:
                    _LOGGER.warning(f"[{self.area}] Failed to calculate data validity from cache: {e}")
        else:
            _LOGGER.debug(f"[{self.area}] No cached data found for decision making.")

        # Instantiate FetchDecisionMaker
        from .fetch_decision import FetchDecisionMaker
        decision_maker = FetchDecisionMaker(tz_service=self._tz_service)

        # Get last fetch time from the shared dictionary for this area
        last_fetch_for_decision = _LAST_FETCH_TIME.get(area_key)

        should_fetch_from_api, fetch_reason = decision_maker.should_fetch(
            now=now,
            last_fetch=last_fetch_for_decision,
            data_validity=data_validity,
            fetch_interval_minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        )

        if not force and not should_fetch_from_api:
            _LOGGER.info(f"Skipping API fetch for area {self.area}: {fetch_reason}")
            if cached_data_for_decision:
                _LOGGER.debug("Returning cached data for %s", self.area)
                # Work on a shallow copy to prevent cache corruption
                # (We only modify top-level keys, so shallow copy is sufficient and much faster)
                data_copy = dict(cached_data_for_decision)
                # Ensure the copied data is marked correctly
                data_copy["using_cached_data"] = True
                # Re-process to ensure current/next prices are updated
                return await self._process_result(data_copy, is_cached=True)
            else:
                # No cache available - this can happen when:
                # 1. Rate-limited with no current interval data (common after config reload/HA restart)
                # 2. Parser/source change invalidated cache
                # 3. First run or cache cleared

                # Check if this is shortly after coordinator creation (config reload/HA restart)
                time_since_creation = now - self._coordinator_created_at
                grace_period = timedelta(minutes=5)  # 5 minute grace period after reload

                if time_since_creation < grace_period and "rate limited" in fetch_reason.lower():
                    # Rate limiting after recent reload - this is expected, log as INFO
                    minutes_until_fetch = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
                    _LOGGER.info(
                        f"[{self.area}] Data will update within {minutes_until_fetch} minutes "
                        f"(rate limit protection active after configuration reload). "
                        f"Reason: {fetch_reason}"
                    )
                else:
                    # Unexpected situation - log as ERROR
                    _LOGGER.error(
                        f"Fetch skipped for {self.area} but no cached data available. "
                        f"Reason: {fetch_reason}"
                    )
                return await self._generate_empty_result(error=f"No cache and no fetch: {fetch_reason}")


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
                        target_date=today_date
                    )
                    if cached_data_rate_limited:
                        _LOGGER.debug("Returning rate-limited cached data for %s (after decision check)", self.area)
                        # Work on a shallow copy to prevent cache corruption
                        # (We only modify top-level keys, so shallow copy is sufficient and much faster)
                        data_copy = dict(cached_data_rate_limited)
                        data_copy["using_cached_data"] = True
                        data_copy["next_fetch_allowed_in_seconds"] = round(next_fetch_allowed_in_seconds, 1)
                        return await self._process_result(data_copy, is_cached=True)
                    else:
                        _LOGGER.error(
                            f"Rate limited for {self.area} (after decision check), no cached data available for today ({today_date}). "
                            f"Next fetch in {next_fetch_allowed_in_seconds:.1f}s"
                        )
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

            # Filter out recently failed sources (within last 24 hours)
            # Unless force=True, which bypasses the 24h filter
            enabled_api_classes = []
            for cls in self._api_classes:
                source_name = cls(config={}).source_type
                last_failure = self._failed_sources.get(source_name)

                # Skip sources that failed recently (within 24 hours), unless forced
                if not force and last_failure and (now - last_failure).total_seconds() < 86400:
                    continue

                enabled_api_classes.append(cls)

            # Log if any sources are skipped
            if len(enabled_api_classes) < len(self._api_classes):
                disabled_count = len(self._api_classes) - len(enabled_api_classes)
                disabled_names = [
                    cls(config={}).source_type for cls in self._api_classes
                    if cls not in enabled_api_classes
                ]
                _LOGGER.info(
                    f"[{self.area}] Skipping {disabled_count} recently failed source(s): {', '.join(disabled_names)} "
                    f"(will retry during daily window)"
                )

            api_instances = [
                cls(
                    config=self.config,
                    session=session,
                    timezone_service=self._tz_service,
                    # Pass other context if needed by base class or specific APIs
                    # hass=self.hass, # Example if HASS instance is needed
                ) for cls in enabled_api_classes
            ]

            if not api_instances:
                _LOGGER.error(f"No API sources available/configured for area {self.area}")
                self._consecutive_failures += 1
                # Try cache before giving up - specify today's date
                cached_data = self._cache_manager.get_data(
                    area=self.area,
                    target_date=today_date # Specify today
                )
                if cached_data:
                    _LOGGER.warning("No APIs available for %s, using cached data.", self.area)
                    cached_data["using_cached_data"] = True
                    processed_cached_data = await self._process_result(cached_data, is_cached=True)
                    processed_cached_data["using_cached_data"] = True # Ensure flag is set
                    return processed_cached_data
                return await self._generate_empty_result(error="No API sources configured")

            # Fetch with fallback using the new manager
            result = await self._fallback_manager.fetch_with_fallback(
                api_instances=api_instances,
                area=self.area,
                reference_time=now,
                session=session,
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

                # Check if processing yielded valid data (either today OR tomorrow prices)
                has_today = processed_data and processed_data.get("interval_prices")
                has_tomorrow = processed_data and processed_data.get("tomorrow_interval_prices")
                has_valid_data = has_today or has_tomorrow

                if processed_data and has_valid_data and "error" not in processed_data:
                    _LOGGER.info(f"[{self.area}] Successfully processed data. Today: {len(processed_data.get('interval_prices', {}))}, Tomorrow: {len(processed_data.get('tomorrow_interval_prices', {}))}")
                    self._consecutive_failures = 0
                    self._active_source = processed_data.get("data_source", "unknown") # Use source from processed data
                    self._attempted_sources = processed_data.get("attempted_sources", [])
                    self._fallback_sources = [s for s in self._attempted_sources if s != self._active_source]
                    self._using_cached_data = False
                    processed_data["using_cached_data"] = False

                    # Track source as successful (clear any failure timestamp)
                    validated_source = self._active_source
                    if validated_source and validated_source not in ("unknown", "None", None):
                        # Clear failure timestamp (None = source is working)
                        self._failed_sources[validated_source] = None
                        _LOGGER.debug(f"[{self.area}] Source '{validated_source}' marked as working")

                    # Cache the successfully processed data
                    self._cache_manager.store(
                        data=processed_data,
                        area=self.area,
                        source=processed_data.get("data_source", "unknown"),
                        timestamp=now
                    )
                    return processed_data
                else:
                    # Processing failed to produce interval_raw or marked as no data
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

            # Implicit validation: Mark all attempted sources as failed and schedule daily retry
            if self._attempted_sources:
                _LOGGER.info(
                    f"[{self.area}] Marking {len(self._attempted_sources)} failed source(s): "
                    f"{', '.join(self._attempted_sources)}"
                )
                for source_name in self._attempted_sources:
                    # Mark source as failed with current timestamp
                    self._failed_sources[source_name] = now

                    # Schedule daily retry if not already scheduled
                    if source_name not in self._retry_scheduled:
                        _LOGGER.info(f"[{self.area}] Scheduling daily retry for '{source_name}'")
                        # Find the API class for this source
                        for cls in self._api_classes:
                            if cls(config={}).source_type == source_name:
                                asyncio.create_task(
                                    self._schedule_daily_retry(source_name, cls)
                                )
                                self._retry_scheduled.add(source_name)
                                break

            # Try to use cached data as a last resort - specify today's date
            cached_data = self._cache_manager.get_data(
                area=self.area,
                target_date=today_date # Specify today
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
                target_date=today_date # Specify today
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
            # Set has_data flag if we have either today OR tomorrow prices
            has_today = bool(processed_data.get("interval_prices"))
            has_tomorrow = bool(processed_data.get("tomorrow_interval_prices"))
            processed_data["has_data"] = has_today or has_tomorrow
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

            # Add validated sources (what's been tested and working)
            processed_data["validated_sources"] = self.get_validated_sources()

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
            "interval_prices": {},
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
            "price_in_cents": False,
            "validated_sources": self.get_validated_sources(),
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
        """Clear the price cache and immediately fetch fresh data."""
        # Clear the cache first (synchronous operation)
        cleared = self._cache_manager.clear_cache(target_date=target_date)
        if cleared:
            _LOGGER.info("Cache cleared for all areas. Forcing fresh fetch for area %s.", self.area)
            # Force a new fetch - this will return fresh data
            fresh_data = await self.fetch_data(force=True)
            _LOGGER.debug(f"Fresh data fetched after cache clear: has_data={fresh_data.get('has_data')}")
            return fresh_data
        return None

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

                 # Check if this is a rate limit situation shortly after coordinator creation
                 time_since_creation = datetime.now(tz=dt_util.UTC) - self.price_manager._coordinator_created_at
                 grace_period = timedelta(minutes=5)

                 if time_since_creation < grace_period and "rate limited" in error_msg.lower():
                     # Rate limiting after recent reload - log as DEBUG, not WARNING
                     _LOGGER.debug(
                         "Update pending for area %s: %s (rate limit protection after reload)",
                         self.area, error_msg
                     )
                 else:
                     # Unexpected situation - log as WARNING
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
        """Clear the price cache and force immediate refresh with fresh data."""
        # Call the manager's clear_cache which fetches fresh data
        fresh_data = await self.price_manager.clear_cache(target_date=target_date)
        if fresh_data:
            _LOGGER.info("Cache cleared and fresh data fetched for area %s", self.area)
            # Directly update coordinator data with the fresh result
            self.async_set_updated_data(fresh_data)
            return True
        return False

    async def async_close(self):
        """Close any open sessions and resources via the manager."""
        await self.price_manager.async_close()
        _LOGGER.debug("Closed resources for coordinator %s", self.area)

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
from ..utils.exchange_service import ExchangeService, get_exchange_service # Import get_exchange_service
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
        self._validated_sources = set()  # Sources that have successfully returned usable data
        self._disabled_sources = set()  # Sources that failed validation (temporarily disabled)
        self._energy_charts_validation_task = None  # Track background validation task

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
        """Get list of validated source names."""
        return sorted(list(self._validated_sources))

    def get_disabled_sources(self) -> List[str]:
        """Get list of disabled source names (failed validation)."""
        return sorted(list(self._disabled_sources))
    
    def get_enabled_sources(self) -> List[str]:
        """Get list of currently enabled source names."""
        all_sources = [cls(config={}).source_type for cls in self._api_classes]
        return sorted([s for s in all_sources if s not in self._disabled_sources])

    async def validate_configured_sources_once(self) -> Dict[str, bool]:
        """Validate all configured sources during initial setup (one-time only).
        
        Fetches actual data with minimal date range (today only) to verify:
        - API is accessible
        - API keys are valid
        - Data can be fetched and parsed
        
        Strategy:
        - Reliable sources (Nordpool, OMIE, etc.): Blocking validation with data caching
        - Energy Charts: Non-blocking background validation (doesn't delay startup)
        
        Called ONLY during initial configuration, not on every restart.
        Failures are logged but don't block setup.
        Runs reliable sources in parallel for speed, Energy Charts in background.
        
        Returns:
            Dict mapping source names to validation results
        """
        session = async_get_clientsession(self.hass)
        now = dt_util.now()
        today_date = now.date()
        
        _LOGGER.info(f"[{self.area}] Validating {len(self._api_classes)} configured source(s)")
        
        # Separate slow sources from reliable sources
        reliable_sources = []
        slow_source_apis = []
        
        for api_class in self._api_classes:
            temp_instance = api_class(config={})
            if temp_instance.source_type in Source.SLOW_SOURCES:
                slow_source_apis.append(api_class)
            else:
                reliable_sources.append(api_class)
        
        async def validate_single_source(api_class, timeout=None):
            """Validate a single API source.
            
            Args:
                api_class: The API class to validate
                timeout: Optional timeout override. If None, uses Network.Defaults.TIMEOUT
            """
            temp_instance = api_class(config={})
            source_name = temp_instance.source_type
            
            # Use configured timeout if not overridden
            if timeout is None:
                timeout = Network.Defaults.TIMEOUT
            
            try:
                api_instance = api_class(
                    config=self.config,
                    session=session,
                    timezone_service=self._tz_service
                )
                
                # Fetch minimal data (today only) with timeout
                data = await asyncio.wait_for(
                    api_instance.fetch_raw_data(
                        area=self.area,
                        session=session,
                        reference_time=now
                    ),
                    timeout=timeout
                )
                
                # Generic validation: Check raw_data exists and is not empty
                raw_data = data.get('raw_data') if data and isinstance(data, dict) else None
                is_valid = raw_data is not None and raw_data  # Not None and not empty
                
                if is_valid:
                    self._validated_sources.add(source_name)
                    # Remove from disabled if it was previously disabled
                    self._disabled_sources.discard(source_name)
                    
                    # Store validated data in cache immediately
                    # This prevents redundant fetches in async_config_entry_first_refresh()
                    try:
                        self._cache_manager.store(
                            area=self.area,
                            source=source_name,
                            data=data,
                            target_date=today_date
                        )
                        _LOGGER.info(f"[{self.area}] ✓ '{source_name}' validated and cached")
                    except Exception as cache_err:
                        _LOGGER.warning(f"[{self.area}] ✓ '{source_name}' validated but cache failed: {cache_err}")
                else:
                    # Disable source that failed validation
                    self._disabled_sources.add(source_name)
                    _LOGGER.warning(
                        f"[{self.area}] ✗ '{source_name}' validation failed - source disabled "
                        f"(will retry daily during special hours)"
                    )
                
                return (source_name, is_valid, data if is_valid else None)
                    
            except asyncio.TimeoutError:
                # Disable source that timed out during validation
                self._disabled_sources.add(source_name)
                _LOGGER.warning(
                    f"[{self.area}] ✗ '{source_name}' validation timeout after {timeout}s - source disabled "
                    f"(will retry daily during special hours)"
                )
                return (source_name, False, None)
            except Exception as e:
                # Disable source that errored during validation
                self._disabled_sources.add(source_name)
                _LOGGER.warning(
                    f"[{self.area}] ✗ '{source_name}' validation error: {e} - source disabled "
                    f"(will retry daily during special hours)"
                )
                return (source_name, False, None)
        
        # Validate reliable sources in parallel (BLOCKING - wait for results)
        _LOGGER.info(f"[{self.area}] Validating {len(reliable_sources)} reliable source(s)...")
        results = await asyncio.gather(
            *[validate_single_source(api_class) for api_class in reliable_sources],
            return_exceptions=True
        )
        
        # Start slow source validation in background (NON-BLOCKING)
        if slow_source_apis:
            slow_source_names = [api_class(config={}).source_type for api_class in slow_source_apis]
            _LOGGER.info(
                f"[{self.area}] Starting background validation for {len(slow_source_apis)} slow source(s): "
                f"{', '.join(slow_source_names)}"
            )
            self._energy_charts_validation_task = asyncio.create_task(
                self._validate_slow_sources_background(slow_source_apis, validate_single_source)
            )
        
        # Convert results to dict and schedule retries for failed sources
        validation_results = {}
        failed_reliable_sources = []
        
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.error(f"[{self.area}] Validation task failed: {result}")
                continue
            if not isinstance(result, tuple) or len(result) != 3:
                _LOGGER.error(f"[{self.area}] Invalid validation result format: {result}")
                continue
            source_name, is_valid, data = result
            validation_results[source_name] = is_valid
            
            # Track failed reliable sources for daily retry
            if not is_valid:
                # Find the API class for this failed source
                for api_class in reliable_sources:
                    if api_class(config={}).source_type == source_name:
                        failed_reliable_sources.append(api_class)
                        break
        
        # Schedule daily retry for failed reliable sources
        if failed_reliable_sources:
            failed_names = [cls(config={}).source_type for cls in failed_reliable_sources]
            _LOGGER.info(
                f"[{self.area}] Scheduling daily retry for {len(failed_reliable_sources)} "
                f"failed reliable source(s): {', '.join(failed_names)}"
            )
            asyncio.create_task(
                self._validate_failed_sources_background(failed_reliable_sources, validate_single_source, is_slow=False)
            )
        
        validated_count = sum(1 for v in validation_results.values() if v)
        total_checked = len(validation_results)
        
        status_msg = f"[{self.area}] Validation: {validated_count}/{total_checked} reliable sources validated"
        if slow_source_apis:
            slow_names = ', '.join(api_class(config={}).source_type for api_class in slow_source_apis)
            status_msg += f" ({slow_names} validating in background)"
        
        if validated_count > 0:
            _LOGGER.info(status_msg)
        else:
            _LOGGER.warning(f"{status_msg} - no sources validated successfully")
        
        return validation_results

    async def _validate_slow_sources_background(self, api_classes, validate_func):
        """Validate slow/unreliable sources in background without blocking startup.
        
        Slow sources (defined in Source.SLOW_SOURCES) get special treatment:
        - Longer timeout (Network.Defaults.SLOW_SOURCE_TIMEOUT)
        - Non-blocking validation (runs in background)
        - Daily retry on failure during special hours
        
        This prevents slow/unreliable APIs from blocking Home Assistant startup.
        
        Args:
            api_classes: List of slow source API classes to validate
            validate_func: The validation function to use
        """
        await self._validate_failed_sources_background(api_classes, validate_func, is_slow=True)

    async def _validate_failed_sources_background(self, api_classes, validate_func, is_slow=False):
        """Validate failed sources in background and schedule daily retries.
        
        Failed sources (both slow and reliable) are validated in background to prevent blocking:
        - Slow sources: Use SLOW_SOURCE_TIMEOUT (120s)
        - Reliable sources: Use standard TIMEOUT (30s)
        - Both: Daily retry on failure during special hours
        
        Args:
            api_classes: List of failed source API classes to validate
            validate_func: The validation function to use
            is_slow: Whether these are slow sources (affects timeout)
        """
        timeout = Network.Defaults.SLOW_SOURCE_TIMEOUT if is_slow else Network.Defaults.TIMEOUT
        source_type = "slow" if is_slow else "reliable"
        
        for api_class in api_classes:
            temp_instance = api_class(config={})
            source_name = temp_instance.source_type
            
            _LOGGER.info(
                f"[{self.area}] Background validation starting for '{source_name}' "
                f"({source_type} source, {timeout}s timeout)"
            )
            
            try:
                # Initial validation attempt (non-blocking for startup)
                result = await validate_func(api_class, timeout=timeout)
                source_name, is_valid, data = result
                
                if is_valid:
                    _LOGGER.info(f"[{self.area}] ✓ '{source_name}' background validation successful")
                else:
                    _LOGGER.warning(
                        f"[{self.area}] ✗ '{source_name}' background validation failed - "
                        f"will retry daily"
                    )
                    
                    # Schedule daily retry during special hours
                    asyncio.create_task(
                        self._schedule_daily_source_retry(api_class, validate_func, source_name, is_slow)
                    )
                    
            except Exception as e:
                _LOGGER.error(f"[{self.area}] {source_name} background validation error: {e}")
                # Schedule retry even on exception
                asyncio.create_task(
                    self._schedule_daily_source_retry(api_class, validate_func, source_name, is_slow)
                )

    async def _schedule_daily_source_retry(self, api_class, validate_func, source_name, is_slow=False):
        """Schedule daily source validation retry during special hours.
        
        Retries once per 24 hours during configured special hour windows
        (e.g., 13:00-15:00 when most EU markets publish data).
        Random time within window to avoid thundering herd.
        
        Works for both slow and reliable sources:
        - Slow sources: Use SLOW_SOURCE_TIMEOUT (120s)
        - Reliable sources: Use standard TIMEOUT (30s)
        
        Args:
            api_class: The source API class to validate
            validate_func: The validation function to use
            source_name: Name of the source for logging
            is_slow: Whether this is a slow source (affects timeout)
        """
        import random
        
        timeout = Network.Defaults.SLOW_SOURCE_TIMEOUT if is_slow else Network.Defaults.TIMEOUT
        source_type = "slow" if is_slow else "reliable"
        last_retry = None
        
        while True:
            now = dt_util.now()
            
            # Check if we're in special hours and haven't retried today
            current_hour = now.hour
            today_date = now.date()
            
            # Check if current hour is within any special hour window
            # Special hours defined in Network.Defaults.SPECIAL_HOUR_WINDOWS (e.g., 13:00-15:00)
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
                delay_seconds = random.randint(0, ValidationRetry.MAX_RANDOM_DELAY_SECONDS)
                _LOGGER.info(
                    f"[{self.area}] Scheduling '{source_name}' ({source_type}) retry in {delay_seconds}s "
                    f"(daily validation attempt, {timeout}s timeout)"
                )
                await asyncio.sleep(delay_seconds)
                
                # Attempt validation with appropriate timeout for source type
                try:
                    result = await validate_func(api_class, timeout=timeout)
                    returned_source_name, is_valid, data = result
                    
                    if is_valid:
                        _LOGGER.info(
                            f"[{self.area}] ✓ '{source_name}' ({source_type}) daily retry successful - "
                            f"source re-enabled and will be used in next fetch"
                        )
                        return  # Validation succeeded, stop retrying (source already re-enabled by validate_func)
                    else:
                        _LOGGER.warning(
                            f"[{self.area}] ✗ '{source_name}' ({source_type}) daily retry failed - "
                            f"source remains disabled, will try tomorrow"
                        )
                        
                except Exception as e:
                    _LOGGER.warning(f"[{self.area}] '{source_name}' ({source_type}) daily retry error: {e}")
                
                last_retry = now
            
            # Sleep until next check
            await asyncio.sleep(ValidationRetry.RETRY_CHECK_INTERVAL_SECONDS)

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

        # --- Wait for slow source background validation if running ---
        # This prevents duplicate fetches when slow sources are priority #1
        if self._energy_charts_validation_task and not self._energy_charts_validation_task.done():
            _LOGGER.info(
                f"[{self.area}] Waiting for slow source background validation to complete "
                f"(prevents duplicate fetch, max {Network.Defaults.SLOW_SOURCE_VALIDATION_WAIT}s)..."
            )
            try:
                # Wait configured time to avoid blocking too long
                await asyncio.wait_for(
                    self._energy_charts_validation_task,
                    timeout=Network.Defaults.SLOW_SOURCE_VALIDATION_WAIT
                )
                _LOGGER.info(f"[{self.area}] Slow source validation completed, checking cache...")
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    f"[{self.area}] Slow source validation still running after "
                    f"{Network.Defaults.SLOW_SOURCE_VALIDATION_WAIT}s, proceeding with fetch "
                    f"(validation will continue in background)"
                )
            except Exception as e:
                _LOGGER.warning(f"[{self.area}] Slow source validation error: {e}")

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
                # 1. Rate-limited with no current interval data
                # 2. Parser/source change invalidated cache
                # 3. First run or cache cleared
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
            
            # Filter out disabled sources (those that failed validation)
            enabled_api_classes = [
                cls for cls in self._api_classes
                if cls(config={}).source_type not in self._disabled_sources
            ]
            
            # Log if any sources are disabled
            if len(enabled_api_classes) < len(self._api_classes):
                disabled_count = len(self._api_classes) - len(enabled_api_classes)
                disabled_names = [
                    cls(config={}).source_type for cls in self._api_classes
                    if cls(config={}).source_type in self._disabled_sources
                ]
                _LOGGER.info(
                    f"[{self.area}] Skipping {disabled_count} disabled source(s): {', '.join(disabled_names)} "
                    f"(failed validation)"
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

                    # Track source validation
                    validated_source = self._active_source
                    if validated_source and validated_source not in ("unknown", "None", None):
                        if validated_source not in self._validated_sources:
                            self._validated_sources.add(validated_source)
                            _LOGGER.info(f"[{self.area}] Source '{validated_source}' validated")

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

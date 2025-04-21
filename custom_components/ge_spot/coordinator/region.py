"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta, datetime, time
from typing import Any, Dict, Optional, List

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval

from ..price import ElectricityPriceAdapter
from ..price.cache import PriceCache
from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.intervals import SourceIntervals
from ..const.attributes import Attributes
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.network import Network
from ..api import fetch_day_ahead_prices, get_sources_for_region
from ..utils.api_validator import ApiValidator
from ..utils.rate_limiter import RateLimiter
from ..api.base.session_manager import close_session
from ..timezone import TimezoneService
from ..utils.fallback import FallbackManager
from ..utils.exchange_service import get_exchange_service
from ..api.base.data_fetch import is_skipped_response
from .tomorrow_data_manager import TomorrowDataManager
from .today_data_manager import TodayDataManager
from .fetch_decision import FetchDecisionMaker
from .data_processor import DataProcessor
from .api_key_manager import ApiKeyManager
from .cache_manager import CacheManager

_LOGGER = logging.getLogger(__name__)

class RegionPriceCoordinator(DataUpdateCoordinator):
    """Data update coordinator for electricity prices by region."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        update_interval: timedelta,
        config: Dict[str, Any],
    ):
        """Initialize the coordinator."""
        # Use the provided update_interval (Home Assistant's default)
        # This controls how often sensors get updated
        super().__init__(
            hass,
            _LOGGER,
            name=f"gespot_{area}",
            update_interval=update_interval,
        )

        # Store API fetch interval separately - this controls API calls
        source_priority = config.get(Config.SOURCE_PRIORITY, Source.DEFAULT_PRIORITY)
        primary_source = source_priority[0] if source_priority else Source.DEFAULT_PRIORITY[0]
        self._api_fetch_interval = SourceIntervals.get_interval(primary_source)

        self.area = area
        self.currency = currency
        self.config = config
        self.adapter = None
        self._last_successful_data = None
        self.session = None

        # API fetch tracking
        self._last_api_fetch = None
        self._next_scheduled_api_fetch = None
        self._consecutive_failures = 0
        self._last_failure_time = None

        # API key status cache
        self._api_key_status = {}

        # Display settings
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
        self.config[Config.DISPLAY_UNIT] = self.display_unit
        self.config["price_in_cents"] = self.use_subunit

        # API source tracking
        self._supported_sources = get_sources_for_region(area)
        self._active_source = None
        self._attempted_sources = []
        self._today_source = None
        self._tomorrow_source = None
        self._fallback_data = {}

        # Initialize managers and services
        self._cache_manager = CacheManager(hass, config)
        self._tz_service = TimezoneService(hass, area, config)
        self._api_key_manager = ApiKeyManager(hass, config, self.session)
        self._fetch_decision_maker = FetchDecisionMaker(self._tz_service)
        self._data_processor = DataProcessor(hass, area, currency, config, self._tz_service)

        # Initialize data managers
        self._today_data_manager = TodayDataManager(
            hass=hass,
            area=area,
            currency=currency,
            config=config,
            price_cache=self._cache_manager._price_cache,  # Direct access for now
            tz_service=self._tz_service,
            session=self.session
        )

        self._tomorrow_data_manager = TomorrowDataManager(
            hass=hass,
            area=area,
            currency=currency,
            config=config,
            price_cache=self._cache_manager._price_cache,  # Direct access for now
            tz_service=self._tz_service,
            session=self.session,
            refresh_callback=self.async_request_refresh
        )

        # Schedule cache cleanup once a day
        if hass:
            async def _async_cleanup_cache(*_):
                self._cache_manager.cleanup()
            self.cleanup_job = async_track_time_interval(
                hass,
                _async_cleanup_cache,
                timedelta(days=1)
            )

            # Schedule independent tomorrow data check
            # This ensures tomorrow data search continues even when using cached data for today
            async def _async_check_tomorrow_data(*_):
                now = dt_util.now()
                if self._tomorrow_data_manager.should_search(now):
                    _LOGGER.info("Scheduled check for tomorrow's data")
                    await self._tomorrow_data_manager.fetch_data()

            # Check every 5 minutes - the tomorrow data manager will handle rate limiting internally
            self.tomorrow_data_job = async_track_time_interval(
                hass,
                _async_check_tomorrow_data,
                timedelta(minutes=5)
            )

    async def check_api_key_status(self):
        """Check status of configured API keys and report in attributes."""
        self._api_key_status = await self._api_key_manager.check_api_key_status()
        return self._api_key_status

    async def clear_cache(self):
        """Clear the price cache."""
        _LOGGER.info(f"Clearing price cache for area {self.area}")
        return self._cache_manager.clear(self.area)

    async def force_update(self):
        """Force an update regardless of schedule."""
        _LOGGER.info(f"Forcing update for area {self.area}")
        # Force an API fetch on next update
        self._last_api_fetch = None
        await self.async_request_refresh()
        return True

    async def _async_update_data(self):
        """Fetch data from cache or API as appropriate."""
        try:
            # Get current time and hour
            now = dt_util.now()
            hour = now.hour

            # Note: Tomorrow data search is now handled by a separate scheduler
            # This ensures it continues even when using cached data for today

            # Check if we have current hour price in cache
            has_current_hour_price = self._cache_manager.has_current_hour_price(self.area)

            # Determine if we need to fetch today's data from API
            need_api_fetch, api_fetch_reason = self._fetch_decision_maker.should_fetch(
                now=now,
                last_fetch=self._last_api_fetch,
                fetch_interval=self._api_fetch_interval,
                has_current_hour_price=has_current_hour_price
            )

            # Additional rate limiter check for today's data
            if need_api_fetch and has_current_hour_price:
                from ..utils.rate_limiter import RateLimiter
                should_skip, skip_reason = RateLimiter.should_skip_fetch(
                    last_fetched=self._last_api_fetch,
                    current_time=now,
                    consecutive_failures=self._consecutive_failures,
                    last_failure_time=self._last_failure_time,
                    min_interval=self._api_fetch_interval,
                    source=self._active_source,
                    area=self.area
                )

                if should_skip:
                    _LOGGER.debug(f"Rate limiter suggests skipping today's data fetch: {skip_reason}")
                    need_api_fetch = False
                    api_fetch_reason = skip_reason

            # Get current hour key for later use
            current_hour_key = self._tz_service.get_current_hour_key()

            # If we don't need API fetch, use cache
            if not need_api_fetch:
                cache_result = self._cache_manager.get_current_hour_price(self.area)
                data = self._cache_manager.get_data(self.area)

                if not data:
                    _LOGGER.warning(f"Cache returned empty data for {self.area}")
                    # Fall through to API fetch
                    need_api_fetch = True
                    api_fetch_reason = "Cache returned empty data"
                else:
                    # Get current hour using timezone service
                    hour_str = self._tz_service.get_current_hour_key()

                    # Format cache info for debug logging
                    api_tz = cache_result.get('api_timezone', 'unknown')
                    ha_tz = cache_result.get('ha_timezone', str(self.hass.config.time_zone) if self.hass else 'unknown')
                    area_tz = cache_result.get('area_timezone', 'same as HA')
                    tz_diff = f"{api_tz} → {area_tz if area_tz else ha_tz}"
                    price_value = data.get('current_price', 'N/A')
                    cache_date = cache_result.get('date', dt_util.now().strftime("%Y-%m-%d"))

                    # Calculate cache age and API fetch age
                    cache_age = (dt_util.now() - dt_util.parse_datetime(cache_result.get('cached_at', dt_util.now().isoformat()))).total_seconds()
                    api_fetch_age = "unknown"
                    api_fetch_time = "unknown"
                    if "last_api_fetch" in data:
                        try:
                            api_fetch_time = data.get('last_api_fetch')
                            api_fetch_age = f"{(dt_util.now() - dt_util.parse_datetime(api_fetch_time)).total_seconds():.1f}s"
                        except Exception:
                            api_fetch_age = "error calculating"

                    # Get additional values excluding large arrays and already displayed values
                    excluded_keys = [
                        'hourly_prices', 'raw_values', 'raw_prices', 'tomorrow_hourly_prices',
                        'adapter', 'fallback_adapters', 'current_price', 'api_timezone',
                        'ha_timezone', 'area_timezone', 'currency', 'source', 'cached_at', 'last_api_fetch'
                    ]
                    additional_values = {k: v for k, v in data.items()
                                        if k not in excluded_keys
                                        and not isinstance(v, dict)
                                        and not isinstance(v, list)}

                    # Format additional values with each on a new line
                    additional_values_str = ""
                    if additional_values:
                        additional_values_str = "\n" + "\n".join([f"  {k}: {v}" for k, v in additional_values.items()])

                    _LOGGER.debug(
                        f"Using cached price for {self.area}:\n"
                        # Timezone information
                        f"  API timezone: {api_tz}\n"
                        f"  HA timezone: {ha_tz}\n"
                        f"  Area timezone: {area_tz}\n"
                        f"  TZ source: {cache_result.get('tz_source', 'unknown')}\n"
                        # Time information
                        f"  Current hour: {hour_str}\n"
                        f"  Date: {cache_date}\n"
                        f"  Cache age: {cache_age:.1f}s\n"
                        f"  API fetch time: {api_fetch_time}\n"
                        f"  API fetch age: {api_fetch_age}\n"
                        # Price information
                        f"  Price: {price_value}\n"
                        f"  Currency: {cache_result.get('currency', 'unknown')}\n"
                        # Source information
                        f"  Source: {cache_result.get('source', 'unknown')}\n"
                        # DST information
                        f"  DST info: {cache_result.get('dst_info', 'none')}\n"
                        f"  DST transition: {cache_result.get('dst_transition', 'none')}"
                        f"{additional_values_str}"
                    )

                    # Create result with updated prices but preserve adapters from previous fetch
                    if self._last_successful_data and "adapter" in self._last_successful_data:
                        primary_adapter = self._last_successful_data["adapter"]
                        fallback_adapters = self._last_successful_data.get("fallback_adapters", {})

                        # Check if any adapter has valid tomorrow data
                        any_adapter_has_tomorrow = primary_adapter.is_tomorrow_valid()
                        for fb_adapter in fallback_adapters.values():
                            if fb_adapter.is_tomorrow_valid():
                                any_adapter_has_tomorrow = True
                                break

                        result = {
                            "adapter": primary_adapter,
                            "fallback_adapters": fallback_adapters,
                            "current_price": data.get("current_price"),
                            "next_hour_price": data.get("next_hour_price"),
                            "today_stats": data.get("today_stats", self._last_successful_data.get("today_stats", {})),
                            "tomorrow_stats": data.get("tomorrow_stats", self._last_successful_data.get("tomorrow_stats", {})),
                            "tomorrow_valid": any_adapter_has_tomorrow,
                            "last_updated": dt_util.now().isoformat(),
                            "last_api_fetch": self._last_api_fetch.isoformat() if self._last_api_fetch else "Unknown",
                            "next_api_fetch": self._next_scheduled_api_fetch.isoformat() if self._next_scheduled_api_fetch else "Unknown",
                            "api_key_status": self._api_key_status,
                            "raw_values": data.get("raw_values", {}),
                            "source": data.get("source", self._last_successful_data.get("source")),
                            "active_source": data.get("active_source", self._last_successful_data.get("active_source")),
                            "attempted_sources": self._last_successful_data.get("attempted_sources", []),
                            "fallback_sources": self._last_successful_data.get("fallback_sources", []),
                            "ha_timezone": ha_tz,
                            "api_timezone": api_tz,
                            "tz_diff": tz_diff,
                            "dst_info": cache_result.get('dst_info', 'none'),
                            "currency": cache_result.get('currency', 'unknown'),
                            "using_cached_data": True,
                            "current_hour_key": current_hour_key,
                            # Tomorrow data search status
                            "tomorrow_data_search_status": self._tomorrow_data_manager.get_status()
                        }
                        return result

                    # If no previous result with adapter, return cache data directly
                    return data

            # API fetch is needed - reset tracking
            if need_api_fetch:
                _LOGGER.info(f"Fetching new data from API for {self.area} - Reason: {api_fetch_reason}")

                self._active_source = None
                self._attempted_sources = []
                self._fallback_data = {}

                # Use TodayDataManager to fetch data
                result = await self._today_data_manager.fetch_data(api_fetch_reason)

                # If all sources failed or were skipped
                if not result:
                    # Handle case where fetch_data returns None (fix for the error!)
                    _LOGGER.warning(f"No data returned from today_data_manager.fetch_data for area {self.area}")
                    self._consecutive_failures += 1
                    self._last_failure_time = dt_util.now()
                    
                    # Schedule a more frequent retry
                    retry_interval = min(120, 15 * (2 ** min(self._consecutive_failures - 1, 3)))
                    self.update_interval = timedelta(minutes=retry_interval)
                    _LOGGER.info(f"Scheduling retry in {retry_interval} minutes after failure")
                    
                    # Try to use cached data as fallback
                    cache_data = self._cache_manager.get_data(self.area)
                    if cache_data:
                        _LOGGER.info(f"Using cached data for {self.area} after API failure")
                        return self._process_cached_data(cache_data)
                    
                    return None
                
                # Fix for the error: Check if data key exists in result dictionary
                if not result.get("data"):
                    # Check if we have skipped sources
                    skipped_sources = result.get("skipped_sources", [])
                    if skipped_sources:
                        _LOGGER.info(f"Some sources were skipped for area {self.area}: {skipped_sources}")
                        _LOGGER.info(f"This is usually due to missing API keys for those sources.")

                    # Only count as a failure if we have no data
                    self._consecutive_failures += 1
                    self._last_failure_time = dt_util.now()
                    _LOGGER.error(f"Failed to fetch data from any source for area {self.area}")

                    # Schedule a more frequent retry
                    retry_interval = min(120, 15 * (2 ** min(self._consecutive_failures - 1, 3)))
                    self.update_interval = timedelta(minutes=retry_interval)
                    _LOGGER.info(f"Scheduling retry in {retry_interval} minutes after failure")

                    # Try to use cached data as fallback
                    cache_data = self._cache_manager.get_data(self.area)
                    if cache_data:
                        _LOGGER.info(f"Using cached data for {self.area} after API failure")
                        return self._process_cached_data(cache_data)

                    return None

                # Use the successful data
                data = result["data"]
                self._active_source = result["source"]
                self._attempted_sources = result["attempted_sources"]
                self._consecutive_failures = 0

                # Update the update interval based on the active source
                if self._active_source:
                    source_interval = SourceIntervals.get_interval(self._active_source)
                    self._api_fetch_interval = source_interval
                    _LOGGER.info(
                        f"Updated API fetch interval to {source_interval} minutes "
                        f"based on active source: {self._active_source}"
                    )

                # Store fallback data if available
                for fb_source in result.get("fallback_sources", []):
                    if fb_source != result["source"] and f"fallback_data_{fb_source}" in result:
                        self._fallback_data[fb_source] = result[f"fallback_data_{fb_source}"]

                # Store in cache with last API fetch time
                self._cache_manager.store(data, self.area, result["source"], self._last_api_fetch)

                # Update tracker variables for timestamps
                self._last_api_fetch = dt_util.now()
                self._next_scheduled_api_fetch = self._last_api_fetch + timedelta(minutes=self._api_fetch_interval)

                # Create adapters for primary and fallback sources
                primary_adapter, fallback_adapters = self._today_data_manager.get_adapters(data)

                # Process the API result using DataProcessor
                final_result = await self._data_processor.process_api_result(
                    result=result,
                    primary_adapter=primary_adapter,
                    fallback_adapters=fallback_adapters,
                    last_api_fetch=self._last_api_fetch,
                    next_scheduled_api_fetch=self._next_scheduled_api_fetch,
                    api_key_status=self._api_key_status,
                    session=self.session
                )

                # Add tomorrow data search status
                final_result["tomorrow_data_search_status"] = self._tomorrow_data_manager.get_status()

                self._last_successful_data = final_result

                # Update tomorrow data manager with the latest data
                self._tomorrow_data_manager.update_data_status(final_result)

                # Check API key status when fetching fresh data
                await self.check_api_key_status()

                return final_result

        except Exception as err:
            self._consecutive_failures += 1
            self._last_failure_time = dt_util.now()
            _LOGGER.error(f"Error fetching electricity price data: {err}")

            # Schedule a more frequent retry
            retry_interval = min(120, 15 * (2 ** min(self._consecutive_failures - 1, 3)))
            self.update_interval = timedelta(minutes=retry_interval)
            _LOGGER.info(f"Scheduling retry in {retry_interval} minutes after error")

            # Try to use cached data as a fallback
            cache_data = self._cache_manager.get_data(self.area)
            if cache_data:
                _LOGGER.info(f"Using cached data after error for {self.area}")
                return self._process_cached_data(cache_data)

            return None

    def _process_cached_data(self, data):
        """Process cached data to ensure consistent output format."""
        result = self._data_processor.process_cached_data(
            data=data,
            last_api_fetch=self._last_api_fetch,
            next_scheduled_api_fetch=self._next_scheduled_api_fetch,
            consecutive_failures=self._consecutive_failures
        )

        # Include tomorrow data search status
        result["tomorrow_data_search_status"] = self._tomorrow_data_manager.get_status()

        return result

    # The tomorrow data functionality has been moved to TomorrowDataManager

    async def async_close(self):
        """Close all API sessions and cancel scheduled jobs."""
        # Cancel the tomorrow data job if it exists
        if hasattr(self, 'tomorrow_data_job') and self.tomorrow_data_job:
            self.tomorrow_data_job()
            self.tomorrow_data_job = None
            _LOGGER.debug("Cancelled tomorrow data job")

        # Cancel the cleanup job if it exists
        if hasattr(self, 'cleanup_job') and self.cleanup_job:
            self.cleanup_job()
            self.cleanup_job = None
            _LOGGER.debug("Cancelled cache cleanup job")

        # Close the session if it exists
        if self.session:
            await close_session(self)

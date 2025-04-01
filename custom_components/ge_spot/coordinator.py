import asyncio
import datetime
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_AREA,
    CONF_ENABLE_FALLBACK,
    REGION_FALLBACKS,
    FALLBACK_SOURCE_ORDER,
)
from .api.base import BaseEnergyAPI

_LOGGER = logging.getLogger(__name__)

class GSpotDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching energy price data with fallback support."""

    def __init__(self, hass: HomeAssistant, api, update_interval, enable_fallback=False):
        """Initialize."""
        self.api = api
        self.platforms = []
        self._cached_data = None
        self._last_successful_update = None
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3  # Number of errors before using cached data
        self._retry_delay = 300  # 5 minutes delay for retry after error
        self._hass = hass
        self._primary_source = getattr(api, "config", {}).get(CONF_SOURCE)
        self._primary_area = getattr(api, "config", {}).get(CONF_AREA)
        self._enable_fallback = enable_fallback
        self._fallback_apis = {}  # Will store fallback APIs if enabled
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(minutes=update_interval),
        )

    async def setup_fallback_apis(self):
        """Set up fallback APIs if fallback is enabled."""
        if not self._enable_fallback or not self._primary_source or not self._primary_area:
            return
            
        # Check if there are fallback options for this region
        fallbacks = REGION_FALLBACKS.get(self._primary_area, {})
        if not fallbacks:
            _LOGGER.debug(f"No fallback options for area {self._primary_area}")
            return
            
        _LOGGER.debug(f"Setting up fallback APIs for {self._primary_source}/{self._primary_area}")
        
        # Import API factories
        from . import create_api_handler
        
        # For each possible fallback source
        for source, area in fallbacks.items():
            # Skip the primary source
            if source == self._primary_source:
                continue
                
            # Create a config for the fallback API
            fallback_config = {
                CONF_SOURCE: source,
                CONF_AREA: area,
                # Copy other config from primary
                "vat": getattr(self.api, "vat", 0),
            }
            
            # Create the fallback API
            fallback_api = create_api_handler(source, fallback_config)
            if fallback_api:
                self._fallback_apis[source] = fallback_api
                _LOGGER.debug(f"Created fallback API for {source}/{area}")
            
        _LOGGER.info(f"Set up {len(self._fallback_apis)} fallback APIs")

    async def _async_update_data(self):
        """Update data via API with fallback support."""
        try:
            # Ensure fallback APIs are set up if enabled
            if self._enable_fallback and not self._fallback_apis:
                await self.setup_fallback_apis()
            
            # Try primary API first
            data = await self._try_update_with_api(self.api, "primary")
            
            if data:
                # Got data from primary API
                return data
            elif not self._enable_fallback or not self._fallback_apis:
                # No fallback available, use cached data if possible
                return self._handle_api_failure("primary", use_cache=True)
            
            # Try fallback APIs in order
            for source_name in FALLBACK_SOURCE_ORDER:
                if source_name == self._primary_source or source_name not in self._fallback_apis:
                    continue
                    
                fallback_api = self._fallback_apis[source_name]
                data = await self._try_update_with_api(fallback_api, f"fallback ({source_name})")
                
                if data:
                    # Mark data as from fallback
                    data["from_fallback"] = True
                    data["fallback_source"] = source_name
                    return data
            
            # All APIs failed, use cached data if possible
            return self._handle_api_failure("all sources", use_cache=True)
                
        except ConfigEntryAuthFailed as auth_error:
            # Don't retry auth failures - user needs to fix configuration
            _LOGGER.error(
                "Authentication error with %s: %s",
                self.api.__class__.__name__,
                auth_error,
            )
            raise
            
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in coordinator: %s",
                err,
                exc_info=True,
            )
            
            # Try to use cached data
            return self._handle_api_failure("all APIs (exception)", use_cache=True)
    
    async def _try_update_with_api(self, api, api_name):
        """Try to update data using the specified API."""
        try:
            _LOGGER.debug(f"Trying to get data from {api_name} API")
            data = await api.async_get_data()
            
            if data:
                # Update cache with successful data
                self._cached_data = data
                self._last_successful_update = dt.now()
                self._consecutive_errors = 0
                _LOGGER.debug(f"Successfully got data from {api_name} API")
                return data
            else:
                _LOGGER.warning(f"No data received from {api_name} API")
                self._consecutive_errors += 1
                return None
                
        except asyncio.TimeoutError as error:
            _LOGGER.warning(f"Timeout error fetching data from {api_name} API: {error}")
            self._consecutive_errors += 1
            return None
            
        except Exception as err:
            _LOGGER.error(f"Error fetching data from {api_name} API: {err}", exc_info=True)
            self._consecutive_errors += 1
            return None
    
    def _handle_api_failure(self, source_name, use_cache=True):
        """Handle failure to fetch data from API(s)."""
        if use_cache and self._cached_data:
            _LOGGER.warning(
                "Using cached data from %s since %s API is unavailable",
                self._last_successful_update,
                source_name,
            )
            # Mark data as cached
            self._cached_data["from_cache"] = True
            return self._cached_data
        
        # Schedule a retry sooner than regular interval
        if self.update_interval > datetime.timedelta(seconds=self._retry_delay):
            self._schedule_refresh()
            
        raise UpdateFailed(f"No data available from {source_name}")
    
    def _schedule_refresh(self):
        """Schedule a refresh after delay.
        
        This is a non-async method that schedules an async refresh.
        """
        if self.update_interval > datetime.timedelta(seconds=self._retry_delay):
            # Use a shorter delay for retries
            delay = self._retry_delay
        else:
            # Use the standard update interval
            delay = self.update_interval.total_seconds()
        
        # Schedule the refresh task
        self.hass.loop.call_later(delay, lambda: self.hass.async_create_task(self.async_refresh()))
    
    async def close(self):
        """Close all API sessions."""
        # Close primary API
        if self.api:
            await self.api.close()
        
        # Close all fallback APIs
        for api in self._fallback_apis.values():
            if api:
                await api.close()

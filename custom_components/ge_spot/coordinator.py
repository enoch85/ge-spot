"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional, List
import datetime
import json

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .price_adapter import ElectricityPriceAdapter
from .const import (
    DOMAIN,
    CONF_AREA,
    CONF_SOURCE_PRIORITY,
    CONF_ENABLE_FALLBACK,
    DEFAULT_ENABLE_FALLBACK,
    ATTR_LAST_UPDATED,
    ATTR_DATA_SOURCE,
    ATTR_FALLBACK_USED,
)
from .api import create_apis_for_region
from .utils.debug_utils import log_raw_data

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
        super().__init__(
            hass,
            _LOGGER,
            name=f"gespot_{area}",
            update_interval=update_interval,
        )
        self.area = area
        self.currency = currency
        self.config = config
        self.adapter = None
        self._last_successful_data = None
        
        # Create prioritized APIs for this region
        source_priority = config.get(CONF_SOURCE_PRIORITY)
        self._apis = create_apis_for_region(area, config, source_priority)
        self._enable_fallback = config.get(CONF_ENABLE_FALLBACK, DEFAULT_ENABLE_FALLBACK)
        self._active_source = None
        self._active_api = None
        self._fallback_used = False
        self._attempted_sources = []

    async def _async_update_data(self):
        """Fetch data from appropriate API for this region."""
        try:
            _LOGGER.info(f"Updating data for area {self.area} with currency {self.currency}")
            _LOGGER.debug(f"Home Assistant timezone: {self.hass.config.time_zone}")

            # Reset tracking variables
            self._fallback_used = False
            self._active_source = None
            self._active_api = None
            self._attempted_sources = []

            # Fetch data from APIs in priority order
            today_data = None
            
            for api in self._apis:
                api_name = api.__class__.__name__
                api_type = next((s for s in self.config.get(CONF_SOURCE_PRIORITY, []) 
                               if s.lower() in api_name.lower()), "unknown")
                
                _LOGGER.info(f"Attempting to fetch data from {api_name} ({api_type})")
                self._attempted_sources.append(api_type)
                
                try:
                    # Pass Home Assistant instance to the API for timezone handling
                    data = await api.fetch_day_ahead_prices(
                        self.area,
                        self.currency,
                        dt_util.now(),
                        self.hass
                    )
                    
                    if data:
                        today_data = data
                        self._active_source = api_type
                        self._active_api = api
                        if len(self._attempted_sources) > 1:
                            self._fallback_used = True
                        _LOGGER.info(f"Successfully retrieved data from {api_name}")
                        break
                    else:
                        _LOGGER.warning(f"No data retrieved from {api_name}")
                except Exception as e:
                    _LOGGER.error(f"Error fetching data from {api_name}: {e}")

            if not today_data:
                _LOGGER.error(f"Failed to fetch price data from any source. Attempted: {', '.join(self._attempted_sources)}")
                if self._last_successful_data:
                    _LOGGER.warning("Using cached data from last successful update")
                    self._last_successful_data["source_info"] = {
                        "reason": "All API sources failed",
                        "attempted_sources": self._attempted_sources,
                        "using_cached_data": True,
                        "cache_timestamp": self._last_successful_data.get(ATTR_LAST_UPDATED, "unknown")
                    }
                    self._last_successful_data[ATTR_FALLBACK_USED] = True
                    return self._last_successful_data
                return None

            # Log raw values for debugging - raw_today contains hourly prices in JSON format
            if "raw_today" in today_data:
                raw_today = today_data["raw_today"]
                _LOGGER.debug(f"Raw today data for sensor.gespot_current_price_{self.area.lower()}: {len(raw_today)} entries")
                # Log all entries in JSON format as requested
                _LOGGER.debug(f"Complete raw today data: {json.dumps(raw_today)}")

            # Log detailed conversion raw values
            if "raw_values" in today_data:
                raw_values = today_data["raw_values"]
                _LOGGER.debug(f"Raw values (including conversion data) for {self.area}: {json.dumps(raw_values)}")

            # Try to fetch tomorrow's data if after 1 PM
            tomorrow_data = None
            tomorrow_source = None
            now = dt_util.now()

            if now.hour >= 13 and self._active_api:
                try:
                    _LOGGER.info(f"Attempting to fetch tomorrow's data from {self._active_source}")
                    tomorrow_data = await self._active_api.fetch_day_ahead_prices(
                        self.area,
                        self.currency,
                        dt_util.now() + timedelta(days=1),
                        self.hass
                    )
                    
                    if tomorrow_data:
                        tomorrow_source = self._active_source
                        _LOGGER.info(f"Successfully fetched tomorrow's price data from {self._active_source}")
                    else:
                        _LOGGER.warning(f"Tomorrow's price data not available from {self._active_source}")
                        
                        # Try fallbacks for tomorrow data if enabled
                        if self._enable_fallback:
                            for api in self._apis:
                                if api == self._active_api:
                                    continue  # Skip the already-tried active API
                                    
                                api_name = api.__class__.__name__
                                api_type = next((s for s in self.config.get(CONF_SOURCE_PRIORITY, []) 
                                               if s.lower() in api_name.lower()), "unknown")
                                
                                _LOGGER.info(f"Trying fallback for tomorrow's data: {api_name}")
                                
                                try:
                                    tomorrow_data = await api.fetch_day_ahead_prices(
                                        self.area,
                                        self.currency,
                                        dt_util.now() + timedelta(days=1),
                                        self.hass
                                    )
                                    
                                    if tomorrow_data:
                                        tomorrow_source = api_type
                                        _LOGGER.info(f"Successfully retrieved tomorrow's data from fallback API: {api_name}")
                                        break
                                except Exception as e:
                                    _LOGGER.error(f"Error fetching tomorrow's data from {api_name}: {e}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to fetch tomorrow's prices: {e}")
            else:
                _LOGGER.info(f"Not fetching tomorrow's data yet, current hour: {now.hour}")

            # Combine the data
            all_data = []
            if today_data:
                all_data.append(today_data)
            if tomorrow_data:
                all_data.append(tomorrow_data)

            # Create adapter with processed data
            _LOGGER.info("Creating price adapter with fetched data")
            self.adapter = ElectricityPriceAdapter(self.hass, all_data)

            if not self.adapter:
                _LOGGER.error("Failed to create price adapter")
                if self._last_successful_data:
                    return self._last_successful_data
                return None

            # Process statistics for today and tomorrow
            today_stats = self.adapter.get_day_statistics(0)
            tomorrow_stats = self.adapter.get_day_statistics(1) if tomorrow_data else None

            # Build information about data sources
            source_info = {
                "primary_source": self.config.get(CONF_SOURCE_PRIORITY, [])[0] if self.config.get(CONF_SOURCE_PRIORITY) else None,
                "active_source": self._active_source,
                "tomorrow_source": tomorrow_source,
                "fallback_used": self._fallback_used,
                "attempted_sources": self._attempted_sources,
                "timezone": str(self.hass.config.time_zone)
            }

            # Calculate next update time
            next_update = dt_util.now() + self.update_interval

            # Return data that will be passed to sensors
            result = {
                "adapter": self.adapter,
                "current_price": self.adapter.get_current_price(),
                "today": self.adapter.get_today_prices(),
                "tomorrow": self.adapter.get_tomorrow_prices(),
                "today_stats": today_stats,
                "tomorrow_stats": tomorrow_stats,
                "tomorrow_valid": self.adapter.is_tomorrow_valid(),
                ATTR_LAST_UPDATED: dt_util.now().isoformat(),
                "next_update": next_update.isoformat(),
                ATTR_DATA_SOURCE: self._active_source,
                ATTR_FALLBACK_USED: self._fallback_used,
                "source_info": source_info,
                "timezone": str(self.hass.config.time_zone)
            }

            _LOGGER.info(f"Successfully updated data with current price: {result['current_price']}")
            self._last_successful_data = result
            return result

        except Exception as err:
            _LOGGER.error(f"Error fetching electricity price data: {err}")
            if self._last_successful_data:
                _LOGGER.warning("Using cached data from last successful update")
                return self._last_successful_data
            raise
            
    async def async_close(self):
        """Close all API sessions."""
        for api in self._apis:
            try:
                if hasattr(api, 'close'):
                    await api.close()
            except Exception as e:
                _LOGGER.error(f"Error closing API {api.__class__.__name__}: {e}")

# Legacy coordinator for backward compatibility
ElectricityPriceCoordinator = RegionPriceCoordinator

"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional, List
import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..price import ElectricityPriceAdapter
from ..const import (
    DOMAIN,
    Config,
    Source,
    Attributes,
    Defaults,
    DisplayUnit,
    Network
)
from ..api import fetch_day_ahead_prices, get_sources_for_region
from ..utils.debug_utils import log_raw_data
from ..utils.api_validator import ApiValidator
from ..utils.rate_limiter import RateLimiter
from ..timezone.converters import normalize_price_periods

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
        self._last_primary_check = None
        self.session = None  # Initialize session attribute to None
        self.configured_update_interval = int(config.get(Config.UPDATE_INTERVAL, Defaults.UPDATE_INTERVAL))

        # Rate limiting state
        self._last_api_fetch = None  # Track last successful API fetch time
        self._consecutive_failures = 0
        self._last_failure_time = None
        
        # API key status cache
        self._api_key_status = {}

        # Ensure display unit is available
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS

        # Make sure all APIs use consistent settings for display unit
        self.config[Config.DISPLAY_UNIT] = self.display_unit
        self.config["price_in_cents"] = self.use_subunit

        # Get supported sources for this region
        self._supported_sources = get_sources_for_region(area)
        self._active_source = None
        self._fallback_used = False
        self._attempted_sources = []

        # Track separate sources for today and tomorrow data
        self._today_source = None
        self._tomorrow_source = None

    async def check_api_key_status(self):
        """Check status of configured API keys and report in attributes."""
        api_key_status = {}

        # Check for ENTSO-E API key
        if Source.ENTSO_E in self.config.get(Config.SOURCE_PRIORITY, []):
            api_key = self.config.get(Config.API_KEY)

            if api_key:
                try:
                    # Import the API module directly
                    from ..api import entsoe
                    
                    # Pass the area parameter and session
                    is_valid = await entsoe.validate_api_key(api_key, self.area, self.session)
                    api_key_status[Source.ENTSO_E] = {
                        "configured": True,
                        "valid": is_valid,
                        "status": "valid" if is_valid else "invalid"
                    }
                    _LOGGER.debug(f"ENTSO-E API key status: {api_key_status[Source.ENTSO_E]}")
                except Exception as e:
                    _LOGGER.error(f"Error validating ENTSO-E API key: {e}")
                    api_key_status[Source.ENTSO_E] = {
                        "configured": True,
                        "valid": False,
                        "status": "error",
                        "error": str(e)
                    }
            else:
                api_key_status[Source.ENTSO_E] = {
                    "configured": False,
                    "valid": None,
                    "status": "not_configured"
                }

        self._api_key_status = api_key_status
        return api_key_status

    def _get_cached_result(self):
        """Get a cached result with updated metadata."""
        if not self._last_successful_data:
            return None
            
        updated_data = dict(self._last_successful_data)
        
        # Update timestamps
        updated_data[Attributes.LAST_UPDATED] = dt_util.now().isoformat()
        updated_data["next_update"] = (dt_util.now() + self.update_interval).isoformat()
        
        # Explicitly mark as cached data
        updated_data["using_cached_data"] = True
        
        # Use cached API key status
        updated_data[Attributes.API_KEY_STATUS] = self._api_key_status
        
        # Update source info to reflect cached status
        if "source_info" in updated_data:
            updated_data["source_info"]["using_cached_data"] = True
            
        return updated_data

    async def _async_update_data(self):
        """Fetch data from appropriate API for this region."""
        try:
            current_time = dt_util.now()

            # Check if we should skip API fetch due to rate limiting
            should_skip, reason = RateLimiter.should_skip_fetch(
                self._last_api_fetch, 
                current_time,
                consecutive_failures=self._consecutive_failures,
                last_failure_time=self._last_failure_time,
                last_successful_fetch=self._last_successful_data,
                configured_interval=self.configured_update_interval
            )
            
            if should_skip and self._last_successful_data and self.adapter:
                _LOGGER.debug(f"Skipping API fetch for area {self.area}: {reason}")
                # Return cached data without rebuilding adapter
                return self._get_cached_result()
                
            # Only log at INFO level when actually making an API call
            _LOGGER.info(f"Updating data for area {self.area} with currency {self.currency}")

            # Reset tracking variables
            self._fallback_used = False
            self._active_source = None
            self._attempted_sources = []
            self._today_source = None
            self._tomorrow_source = None

            # Store results by source and date
            source_data = {
                "today": {},
                "tomorrow": {}
            }

            # Get source priorities
            source_priority = self.config.get(Config.SOURCE_PRIORITY, [])
            if not source_priority:
                source_priority = self._supported_sources

            # Flag to track if any source fetched fresh data
            fetched_fresh_data = False

            # Try to fetch data from sources in priority order
            for source in source_priority:
                if source not in self._supported_sources:
                    continue
                    
                self._attempted_sources.append(source)
                _LOGGER.info(f"Attempting to fetch data from {source}")

                try:
                    # Setup config for this fetch
                    api_config = dict(self.config)
                    api_config["session"] = self.session
                    
                    # For first source only, try to fetch fresh data
                    if source == source_priority[0]:
                        # Try to get fresh data from primary source
                        data = await fetch_day_ahead_prices(
                            source, 
                            api_config, 
                            self.area, 
                            self.currency, 
                            dt_util.now(), 
                            self.hass
                        )
                    else:
                        # For fallback sources, always allow cached data
                        # We've already decided to fetch, but secondary sources can use cache
                        data = await fetch_day_ahead_prices(
                            source, 
                            api_config, 
                            self.area, 
                            self.currency, 
                            dt_util.now(), 
                            self.hass
                        )

                    # If data is valid, store it
                    if data and ApiValidator.is_data_adequate(data):
                        # Normalize timestamps to Home Assistant timezone
                        if "raw_prices" in data:
                            data["raw_prices"] = normalize_price_periods(data["raw_prices"], self.hass)
                            
                        # Check if data is fresh (not from cache)
                        if not data.get("using_cached_data", False):
                            fetched_fresh_data = True
                            
                        source_data["today"][source] = data
                        self._today_source = source
                        
                        # If this is the first successful source, set as active
                        if not self._active_source:
                            self._active_source = source
                            self._fallback_used = source != source_priority[0]
                            # Reset failure counter if we got data
                            self._consecutive_failures = 0

                        # Check for tomorrow data
                        if data.get("tomorrow_valid", False) or "tomorrow_hourly_prices" in data:
                            source_data["tomorrow"][source] = data
                            self._tomorrow_source = source
                            
                        # If we got data from first source, don't try fallbacks for today's data
                        if source == source_priority[0]:
                            # Try separate fetch for tomorrow data if primary source doesn't have it
                            if not (data.get("tomorrow_valid", False) or "tomorrow_hourly_prices" in data):
                                for fallback_source in source_priority[1:]:
                                    if fallback_source not in self._supported_sources:
                                        continue
                                        
                                    try:
                                        _LOGGER.debug(f"Attempting to fetch tomorrow data from {fallback_source}")
                                        fallback_config = dict(self.config)
                                        fallback_config["session"] = self.session
                                        
                                        # Create a reference time for tomorrow
                                        tomorrow = dt_util.now() + datetime.timedelta(days=1)
                                        tomorrow_data = await fetch_day_ahead_prices(
                                            fallback_source, 
                                            fallback_config, 
                                            self.area, 
                                            self.currency, 
                                            tomorrow, 
                                            self.hass
                                        )
                                        
                                        if tomorrow_data and (tomorrow_data.get("tomorrow_valid", False) or 
                                                           "tomorrow_hourly_prices" in tomorrow_data or
                                                           len(tomorrow_data.get("hourly_prices", {})) > 0):
                                            # Normalize timestamps
                                            if "raw_prices" in tomorrow_data:
                                                tomorrow_data["raw_prices"] = normalize_price_periods(
                                                    tomorrow_data["raw_prices"], self.hass
                                                )
                                            
                                            # Clear current/next price fields from tomorrow data to prevent confusion
                                            tomorrow_data.pop("current_price", None)
                                            tomorrow_data.pop("next_hour_price", None)
                                            if "raw_values" in tomorrow_data:
                                                tomorrow_data["raw_values"].pop("current_price", None)
                                                tomorrow_data["raw_values"].pop("next_hour_price", None)
                                            
                                            source_data["tomorrow"][fallback_source] = tomorrow_data
                                            self._tomorrow_source = fallback_source
                                            break
                                    except Exception as e:
                                        _LOGGER.error(f"Error fetching tomorrow data from {fallback_source}: {e}")
                            
                            # Done with primary source
                            break
                            
                except Exception as e:
                    _LOGGER.error(f"Error fetching data from {source}: {e}")
                    # Count as failure only for primary source
                    if source == source_priority[0]:
                        self._consecutive_failures += 1
                        self._last_failure_time = current_time

            # Update last fetch time if we got fresh data
            if fetched_fresh_data:
                self._last_api_fetch = current_time
                _LOGGER.debug(f"Updated last API fetch time to {self._last_api_fetch.isoformat()}")

            # If we couldn't get today's data from any source
            if not source_data["today"]:
                _LOGGER.error(f"Failed to fetch today's price data. Attempted: {', '.join(self._attempted_sources)}")
                if self._last_successful_data and self.adapter:
                    _LOGGER.warning("Using cached data from last successful update")
                    return self._get_cached_result()
                return None

            # Choose the best sources for today and tomorrow
            today_data = self._select_primary_source_data(source_data["today"])

            # If tomorrow data is available from today's source, use it
            if today_data.get("tomorrow_valid", False) or "tomorrow_hourly_prices" in today_data:
                tomorrow_data = today_data
                _LOGGER.info(f"Using tomorrow data from same source: {self._today_source}")
            else:
                # Select tomorrow data from fallback sources if available
                tomorrow_data = self._select_best_tomorrow_data(source_data["tomorrow"])
                if tomorrow_data:
                    _LOGGER.info(f"Using tomorrow data from fallback source: {self._tomorrow_source}")
                else:
                    _LOGGER.info("No tomorrow data available from any source")

            # Combine today and tomorrow data
            all_data = []
            if today_data:
                all_data.append(today_data)
            if tomorrow_data and tomorrow_data != today_data:
                all_data.append(tomorrow_data)

            # Create adapter with processed data and pass display unit setting
            _LOGGER.info("Creating price adapter with fetched data")
            self.adapter = ElectricityPriceAdapter(
                self.hass, 
                all_data, 
                self.use_subunit,
                using_cached_data=not fetched_fresh_data  # Pass the cached status flag
            )

            if not self.adapter:
                _LOGGER.error("Failed to create price adapter")
                if self._last_successful_data and self.adapter:
                    return self._get_cached_result()
                return None

            # Process statistics for today and tomorrow
            today_stats = self.adapter.get_day_statistics(0)
            tomorrow_stats = self.adapter.get_day_statistics(1) if self.adapter.classified_periods["tomorrow"] else None

            # Get available fallbacks (sources after the primary)
            available_fallbacks = []
            for source in source_priority[1:]:
                if source in self._supported_sources:
                    available_fallbacks.append(source)

            # Build information about data sources
            source_info = {
                "primary_source": source_priority[0] if source_priority else None,
                "active_source": self._active_source,
                "today_source": self._today_source,
                "tomorrow_source": self._tomorrow_source,
                "fallback_used": self._fallback_used,
                "is_using_fallback": self._fallback_used,
                "attempted_sources": self._attempted_sources,
                "available_fallbacks": available_fallbacks,
                "timezone": str(self.hass.config.time_zone),
                "last_api_fetch": self._last_api_fetch.isoformat() if self._last_api_fetch else None,
                "using_cached_data": not fetched_fresh_data,
                "rate_limit_status": {
                    "consecutive_failures": self._consecutive_failures,
                    "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None
                }
            }

            # Calculate next update time
            next_update = dt_util.now() + self.update_interval

            # Check API key status only when fetching fresh data
            if fetched_fresh_data:
                self._api_key_status = await self.check_api_key_status()

            # Get exchange rate info
            try:
                from ..utils.exchange_service import get_exchange_service
                exchange_service = await get_exchange_service(self.session)
                exchange_rate_info = exchange_service.get_exchange_rate_info("EUR", self.currency)
                
                # Add exchange info directly to source_info
                source_info["ECB_Rate"] = exchange_rate_info.get("formatted")  
                source_info["ECB_Updated"] = exchange_rate_info.get("timestamp")
            except Exception as e:
                _LOGGER.error(f"Error getting exchange rate (ECB) info: {e}")
                source_info["ECB_error"] = str(e)

            # Build result data for sensors - remove duplicated attributes
            result = {
                "adapter": self.adapter,
                "current_price": self.adapter.get_current_price(),
                "today": self.adapter.get_today_prices(),
                "tomorrow": self.adapter.get_tomorrow_prices(),
                "today_stats": today_stats,
                "tomorrow_stats": tomorrow_stats,
                "tomorrow_valid": self.adapter.is_tomorrow_valid(),
                Attributes.LAST_UPDATED: dt_util.now().isoformat(),
                "next_update": next_update.isoformat(),
                Attributes.API_KEY_STATUS: self._api_key_status,
                "source_info": source_info,
                "display_unit": self.display_unit,
                "use_subunit": self.use_subunit,
                # Include raw values from the source if available
                "raw_values": today_data.get("raw_values", {}),
                # Mark whether we used cached data
                "using_cached_data": not fetched_fresh_data
            }

            _LOGGER.info(f"Successfully updated data with current price: {result['current_price']}")
            self._last_successful_data = result
            return result

        except Exception as err:
            self._consecutive_failures += 1
            self._last_failure_time = dt_util.now()
            _LOGGER.error(f"Error fetching electricity price data: {err}")
            
            if self._last_successful_data and self.adapter:
                _LOGGER.warning("Using cached data from last successful update")
                return self._get_cached_result()
            raise

    def _select_primary_source_data(self, source_data):
        """Select the best source for today's data based on priority."""
        if not source_data:
            return None

        # Get source priorities from config
        priorities = self.config.get(Config.SOURCE_PRIORITY, [])

        # Try to find data from sources in priority order
        for source in priorities:
            if source in source_data:
                self._today_source = source
                return source_data[source]

        # If no priority match, just use the first available
        first_source = next(iter(source_data.keys()))
        self._today_source = first_source
        return source_data[first_source]

    def _select_best_tomorrow_data(self, source_data):
        """Select the best source for tomorrow's data."""
        if not source_data:
            return None

        # If today's source has tomorrow data, prefer that for consistency
        if self._today_source and self._today_source in source_data:
            self._tomorrow_source = self._today_source
            return source_data[self._today_source]

        # Otherwise, use priority order
        priorities = self.config.get(Config.SOURCE_PRIORITY, [])
        for source in priorities:
            if source in source_data:
                self._tomorrow_source = source
                return source_data[source]

        # Fallback to first available
        if source_data:
            first_source = next(iter(source_data.keys()))
            self._tomorrow_source = first_source
            return source_data[first_source]
            
        return None

    async def async_close(self):
        """Close all API sessions."""
        if self.session:
            try:
                await self.session.close()
                self.session = None
            except Exception as e:
                _LOGGER.error(f"Error closing session: {e}")

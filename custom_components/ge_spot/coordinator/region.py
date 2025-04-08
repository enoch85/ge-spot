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
    DisplayUnit
)
from ..api import create_apis_for_region
from ..utils.debug_utils import log_raw_data
from ..utils.api_validator import ApiValidator

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

        # Create prioritized APIs for this region
        source_priority = config.get(Config.SOURCE_PRIORITY)

        # Ensure display unit is available to all APIs
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS

        # Make sure all APIs use consistent settings for display unit
        self.config["price_in_cents"] = self.use_subunit

        self._apis = create_apis_for_region(area, config, source_priority)
        self._active_source = None
        self._active_api = None
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
                # Try to find the ENTSO-E API instance
                entsoe_api = next((api for api in self._apis
                              if Source.ENTSO_E.lower() in api.__class__.__name__.lower()), None)

                if entsoe_api and hasattr(entsoe_api, "validate_api_key"):
                    try:
                        # Get session from the API if possible
                        session = getattr(entsoe_api, 'session', None)

                        # Pass the area parameter and the session from the API if available
                        is_valid = await entsoe_api.validate_api_key(api_key, self.area, session)
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
                        "configured": True,
                        "valid": None,
                        "status": "unknown"
                    }
            else:
                api_key_status[Source.ENTSO_E] = {
                    "configured": False,
                    "valid": None,
                    "status": "not_configured"
                }

        return api_key_status

    async def _async_update_data(self):
        """Fetch data from appropriate API for this region."""
        try:
            _LOGGER.info(f"Updating data for area {self.area} with currency {self.currency}")
            _LOGGER.debug(f"Home Assistant timezone: {self.hass.config.time_zone}")
            _LOGGER.debug(f"Using display unit: {self.display_unit}, subunit conversion: {self.use_subunit}")

            # Reset tracking variables
            self._fallback_used = False
            self._active_source = None
            self._active_api = None
            self._attempted_sources = []
            self._today_source = None
            self._tomorrow_source = None

            # Store results by source and date
            source_data = {
                "today": {},
                "tomorrow": {}
            }

            # Try to fetch data from all available sources
            for api in self._apis:
                api_name = api.__class__.__name__
                source_type = self._map_api_to_source_type(api_name)
                self._attempted_sources.append(source_type)

                _LOGGER.info(f"Attempting to fetch data from {api_name} ({source_type})")

                try:
                    # Pass display unit setting to API
                    api.config[Config.DISPLAY_UNIT] = self.display_unit
                    api.config["price_in_cents"] = self.use_subunit

                    # Pass Home Assistant instance to the API for timezone handling
                    data = await api.fetch_day_ahead_prices(
                        self.area,
                        self.currency,
                        dt_util.now(),
                        self.hass
                    )

                    # If data is valid, store it by source
                    if data and ApiValidator.is_data_adequate(data):
                        source_data["today"][source_type] = data
                        self._today_source = source_type

                        # If this is the first successful source, set as active
                        if not self._active_source:
                            self._active_source = source_type
                            self._active_api = api
                            self._fallback_used = self._active_source != self.config.get(Config.SOURCE_PRIORITY, [])[0]

                        # Check for tomorrow data
                        if data.get("tomorrow_valid", False) or "tomorrow_hourly_prices" in data:
                            source_data["tomorrow"][source_type] = data
                            self._tomorrow_source = source_type

                except Exception as e:
                    _LOGGER.error(f"Error fetching data from {api_name}: {e}")

            # If we couldn't get today's data from any source
            if not source_data["today"]:
                _LOGGER.error(f"Failed to fetch today's price data from any source. Attempted: {', '.join(self._attempted_sources)}")
                if self._last_successful_data:
                    _LOGGER.warning("Using cached data from last successful update")

                    # Check API key status
                    api_key_status = await self.check_api_key_status()
                    self._last_successful_data[Attributes.API_KEY_STATUS] = api_key_status

                    return self._last_successful_data
                return None

            # Choose the best sources for today and tomorrow
            today_data = self._select_primary_source_data(source_data["today"])

            # If tomorrow data is available from today's source, use it
            # Otherwise, choose the best available tomorrow data from any source
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
            self.adapter = ElectricityPriceAdapter(self.hass, all_data, self.use_subunit)

            if not self.adapter:
                _LOGGER.error("Failed to create price adapter")
                if self._last_successful_data:
                    # Check API key status
                    api_key_status = await self.check_api_key_status()
                    self._last_successful_data[Attributes.API_KEY_STATUS] = api_key_status
                    return self._last_successful_data
                return None

            # Process statistics for today and tomorrow
            today_stats = self.adapter.get_day_statistics(0)
            tomorrow_stats = self.adapter.get_day_statistics(1) if self.adapter.classified_periods["tomorrow"] else None

            # Get available fallbacks (sources after the primary)
            available_fallbacks = []
            if len(self._apis) > 1:
                for api in self._apis[1:]:
                    source_type = self._map_api_to_source_type(api.__class__.__name__)
                    available_fallbacks.append(source_type)

            # Build information about data sources
            source_info = {
                "primary_source": self.config.get(Config.SOURCE_PRIORITY, [])[0] if self.config.get(Config.SOURCE_PRIORITY) else None,
                "active_source": self._active_source,
                "today_source": self._today_source,
                "tomorrow_source": self._tomorrow_source,
                "fallback_used": self._fallback_used,
                "is_using_fallback": self._fallback_used,
                "attempted_sources": self._attempted_sources,
                "available_fallbacks": available_fallbacks,
                "timezone": str(self.hass.config.time_zone)
            }

            # Calculate next update time
            next_update = dt_util.now() + self.update_interval

            # Check API key status
            api_key_status = await self.check_api_key_status()

            # Get exchange rate info
            try:
                from ..utils.exchange_service import get_exchange_service
                exchange_service = await get_exchange_service()
                exchange_rate_info = exchange_service.get_exchange_rate_info("EUR", self.currency)
                _LOGGER.debug(f"Exchange rate info: {exchange_rate_info}")
            except Exception as e:
                _LOGGER.error(f"Error getting exchange rate info: {e}")
                exchange_rate_info = {
                    "timestamp": None,
                    "error": str(e)
                }

            # Return data that will be passed to sensors
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
                Attributes.DATA_SOURCE: self._active_source,
                Attributes.FALLBACK_USED: self._fallback_used,
                Attributes.IS_USING_FALLBACK: self._fallback_used,
                Attributes.AVAILABLE_FALLBACKS: available_fallbacks,
                Attributes.API_KEY_STATUS: api_key_status,
                "source_info": source_info,
                "timezone": str(self.hass.config.time_zone),
                "exchange_rate_info": exchange_rate_info,
                "display_unit": self.display_unit,
                "use_subunit": self.use_subunit
            }

            _LOGGER.info(f"Successfully updated data with current price: {result['current_price']}")
            self._last_successful_data = result
            return result

        except Exception as err:
            _LOGGER.error(f"Error fetching electricity price data: {err}")
            if self._last_successful_data:
                _LOGGER.warning("Using cached data from last successful update")

                # Check API key status
                api_key_status = await self.check_api_key_status()
                self._last_successful_data[Attributes.API_KEY_STATUS] = api_key_status

                return self._last_successful_data
            raise

    def _map_api_to_source_type(self, api_name):
        """Map API class name to source type."""
        source_mapping = {
            "NordpoolAPI": Source.NORDPOOL,
            "EntsoEAPI": Source.ENTSO_E,
            "EnergiDataServiceAPI": Source.ENERGI_DATA_SERVICE,
            "EpexAPI": Source.EPEX,
            "OmieAPI": Source.OMIE,
            "AemoAPI": Source.AEMO, 
            "StromligningAPI": Source.STROMLIGNING
        }

        # Try direct mapping first
        if api_name in source_mapping:
            return source_mapping[api_name]

        # Fallback to case-insensitive substring search
        for source, mapped_name in source_mapping.items():
            if source.lower() in api_name.lower():
                return mapped_name

        # If no match, return a generic name based on API class
        return api_name.lower().replace("api", "")

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
        first_source = next(iter(source_data.keys()))
        self._tomorrow_source = first_source
        return source_data[first_source]

    async def async_close(self):
        """Close all API sessions."""
        for api in self._apis:
            try:
                if hasattr(api, 'close'):
                    await api.close()
            except Exception as e:
                _LOGGER.error(f"Error closing API {api.__class__.__name__}: {e}")

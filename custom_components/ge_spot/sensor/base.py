"""Base sensor for electricity prices."""
import logging
from typing import Dict, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..const.attributes import Attributes
from ..const.config import Config
from ..const.currencies import Currency, CurrencyInfo
from ..const.defaults import Defaults
from ..const.display import DisplayUnit # Ensure DisplayUnit is imported
from ..const.network import Network # Import Network

_LOGGER = logging.getLogger(__name__)

class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        if not isinstance(config_data, dict):
            raise TypeError("config_data must be a dictionary")
        self._area = config_data.get(Attributes.AREA)
        self._vat = config_data.get(Attributes.VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type

        # Display settings
        self._display_unit = config_data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT) # Get from config_data
        # Determine if subunit should be used based on the display_unit setting
        self._use_subunit = self._display_unit == DisplayUnit.CENTS # Correctly determine based on _display_unit
        self._currency = config_data.get(Attributes.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(self._area))

        # Create entity ID and name
        if self._area:
            area_lower = self._area.lower()
            self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{area_lower}"
            self._attr_name = f"GE-Spot {name_suffix} {self._area}"
            self._attr_unique_id = f"gespot_{sensor_type}_{area_lower}"
        else:
            # Log an error and potentially set default/invalid values or raise to prevent setup
            _LOGGER.error("Area is not configured or is None. Cannot create sensor entity.")
            # Option 1: Set dummy values (might hide the config issue)
            # self.entity_id = f"sensor.gespot_{sensor_type.lower()}_invalid_area"
            # self._attr_name = f"GE-Spot {name_suffix} (Invalid Area)"
            # self._attr_unique_id = f"gespot_{sensor_type}_invalid_area"
            # Option 2: Raise an error to clearly signal failed setup (might be better)
            raise ValueError("Area configuration is missing, cannot initialize sensor.")


        # Set unit based on display_unit configuration
        if self._use_subunit:
            subunit = CurrencyInfo.SUBUNIT_NAMES.get(self._currency, "cents")
            self._attr_native_unit_of_measurement = f"{subunit}/kWh"
        else:
            self._attr_native_unit_of_measurement = f"{self._currency}/kWh"

        self._attr_suggested_display_precision = self._precision

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        # Initialize attributes dictionary
        attrs = {
            "currency": self._currency,
            "area": self._area,
            "vat": f"{self._vat * 100:.0f}%",
            "display_unit": self._display_unit,
            "use_subunit": self._use_subunit,
            # Corrected: Use 'data_source' from coordinator data
            "data_source": self.coordinator.data.get("data_source", "unknown"),
        }

        # Add timestamps if available
        # Corrected: Use 'last_update' key
        if "last_update" in self.coordinator.data:
            attrs["last_updated"] = self.coordinator.data["last_update"]

        # Corrected: Use 'last_fetch_attempt' key
        if "last_fetch_attempt" in self.coordinator.data:
            attrs["last_api_fetch"] = self.coordinator.data["last_fetch_attempt"]

        # Add source info dictionary (logic previously updated)
        source_info = {}
        active_source = self.coordinator.data.get("data_source")
        attempted_sources = self.coordinator.data.get("attempted_sources")
        primary_source = None

        # Infer primary source from attempted_sources if available
        if attempted_sources and isinstance(attempted_sources, list) and len(attempted_sources) > 0:
            primary_source = attempted_sources[0]
            source_info["primary_source"] = primary_source # Add inferred primary source

        if active_source:
            source_info["active_source"] = active_source # Use data_source as active_source

        if attempted_sources:
            source_info["attempted_sources"] = attempted_sources

        # Calculate fallback status using inferred primary and active source
        if primary_source and active_source:
            source_info["is_using_fallback"] = (active_source != primary_source) and (active_source != "None")
        elif active_source == "None" and primary_source:
            source_info["is_using_fallback"] = True
        else:
            source_info["is_using_fallback"] = False

        # Add fallback sources list if available
        if "fallback_sources" in self.coordinator.data:
            fallback_sources_list = self.coordinator.data["fallback_sources"]
            source_info["fallback_sources"] = fallback_sources_list
            source_info["available_fallbacks"] = len(fallback_sources_list)
        else:
             source_info["fallback_sources"] = []
             source_info["available_fallbacks"] = 0

        # Add API key status if available
        if "api_key_status" in self.coordinator.data:
            source_info["api_key_status"] = self.coordinator.data["api_key_status"]

        # Add rate limit info
        source_info["rate_limit_interval_seconds"] = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES * 60
        if "next_fetch_allowed_in_seconds" in self.coordinator.data:
            source_info["next_fetch_allowed_in_seconds"] = self.coordinator.data["next_fetch_allowed_in_seconds"]

        # Only add source_info if it contains data
        if source_info:
            attrs["source_info"] = source_info

        # Add timezone info
        # Corrected: Use 'target_timezone' key for HA timezone
        if "target_timezone" in self.coordinator.data:
            attrs["ha_timezone"] = self.coordinator.data["target_timezone"]

        # Corrected: Use 'source_timezone' key for API timezone
        if "source_timezone" in self.coordinator.data:
            attrs["api_timezone"] = self.coordinator.data["source_timezone"]

        # Add interval prices if available, rounding float values
        if "interval_prices" in self.coordinator.data:
            interval_prices = self.coordinator.data["interval_prices"]
            if isinstance(interval_prices, dict):
                attrs["interval_prices"] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in interval_prices.items()
                }
            else:
                attrs["interval_prices"] = interval_prices # Keep original if not a dict

        # Add tomorrow interval prices if available, rounding float values
        if "tomorrow_interval_prices" in self.coordinator.data:
            tomorrow_interval_prices = self.coordinator.data["tomorrow_interval_prices"]
            if isinstance(tomorrow_interval_prices, dict):
                attrs["tomorrow_interval_prices"] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in tomorrow_interval_prices.items()
                }
            else:
                attrs["tomorrow_interval_prices"] = tomorrow_interval_prices # Keep original if not a dict

        # Add error message if available
        if "error" in self.coordinator.data and self.coordinator.data["error"]:
            attrs["error"] = self.coordinator.data["error"]

        # Add EV Smart Charging compatibility attributes
        # Only add these for the current_price sensor
        if self._sensor_type == "current_price":
            # Add current_price attribute (the sensor's state value)
            if self.native_value is not None:
                attrs["current_price"] = self.native_value
            
            # Convert interval_prices dict to raw_today array format
            if "interval_prices" in self.coordinator.data:
                interval_prices = self.coordinator.data["interval_prices"]
                if isinstance(interval_prices, dict):
                    raw_today = []
                    for timestamp_str, price in sorted(interval_prices.items()):
                        try:
                            # Parse the timestamp string
                            from datetime import datetime
                            dt = datetime.fromisoformat(timestamp_str)
                            raw_today.append({
                                "time": timestamp_str,
                                "price": round(price, 4) if isinstance(price, float) else price
                            })
                        except (ValueError, TypeError):
                            continue
                    if raw_today:
                        attrs["raw_today"] = raw_today
            
            # Convert tomorrow_interval_prices dict to raw_tomorrow array format
            if "tomorrow_interval_prices" in self.coordinator.data:
                tomorrow_interval_prices = self.coordinator.data["tomorrow_interval_prices"]
                if isinstance(tomorrow_interval_prices, dict) and tomorrow_interval_prices:
                    raw_tomorrow = []
                    for timestamp_str, price in sorted(tomorrow_interval_prices.items()):
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(timestamp_str)
                            raw_tomorrow.append({
                                "time": timestamp_str,
                                "price": round(price, 4) if isinstance(price, float) else price
                            })
                        except (ValueError, TypeError):
                            continue
                    if raw_tomorrow:
                        attrs["raw_tomorrow"] = raw_tomorrow
                else:
                    # Set to None if tomorrow prices aren't available yet
                    attrs["raw_tomorrow"] = None
            else:
                attrs["raw_tomorrow"] = None

        return attrs

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()

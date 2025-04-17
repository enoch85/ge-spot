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
from ..const.display import DisplayUnit

_LOGGER = logging.getLogger(__name__)

class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        self._area = config_data.get(Attributes.AREA)
        self._vat = config_data.get(Attributes.VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type

        # Display settings
        self._display_unit = coordinator.display_unit
        self._use_subunit = coordinator.use_subunit
        self._currency = config_data.get(Attributes.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(self._area))

        # Create entity ID and name
        self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{self._area.lower()}"
        self._attr_name = f"GE-Spot {name_suffix} {self._area}"
        self._attr_unique_id = f"gespot_{sensor_type}_{self._area}".lower()

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
            "data_source": self.coordinator.data.get("source", "unknown"),
        }

        # Add timestamps if available
        if "last_updated" in self.coordinator.data:
            attrs["last_updated"] = self.coordinator.data["last_updated"]

        if "last_api_fetch" in self.coordinator.data:
            attrs["last_api_fetch"] = self.coordinator.data["last_api_fetch"]

        if "next_update" in self.coordinator.data:
            attrs["next_update"] = self.coordinator.data["next_update"]

        # Add raw value if available for current hour only
        if "raw_values" in self.coordinator.data and self._sensor_type in self.coordinator.data["raw_values"]:
            raw_info = self.coordinator.data["raw_values"][self._sensor_type]
            if isinstance(raw_info, dict) and "raw" in raw_info:
                attrs["raw_value"] = raw_info["raw"]
                attrs["raw_unit"] = raw_info.get("unit")

        # Add source info dictionary
        source_info = {}

        # Only add these if they exist
        if "active_source" in self.coordinator.data:
            source_info["active_source"] = self.coordinator.data["active_source"]

        if "attempted_sources" in self.coordinator.data:
            source_info["attempted_sources"] = self.coordinator.data["attempted_sources"]

        if "source" in self.coordinator.data:
            source_info["primary_source"] = self.coordinator.data["source"]

        # Calculate fallback status if we have both values
        if "active_source" in self.coordinator.data and "source" in self.coordinator.data:
            source_info["is_using_fallback"] = self.coordinator.data["active_source"] != self.coordinator.data["source"]

        # Add fallback sources if available
        if "fallback_sources" in self.coordinator.data:
            source_info["fallback_sources"] = self.coordinator.data["fallback_sources"]
            source_info["available_fallbacks"] = len(self.coordinator.data["fallback_sources"])

        # Add API key status if available
        if "api_key_status" in self.coordinator.data:
            source_info["api_key_status"] = self.coordinator.data["api_key_status"]

        # Only add source_info if it contains data
        if source_info:
            attrs["source_info"] = source_info

        # Add timezone info
        if "ha_timezone" in self.coordinator.data:
            attrs["ha_timezone"] = self.coordinator.data["ha_timezone"]

        if "api_timezone" in self.coordinator.data:
            attrs["api_timezone"] = self.coordinator.data["api_timezone"]

        return attrs

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()

"""Base sensor for electricity prices."""
import logging
from typing import Dict, Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    Attributes,
    Config,
    Currency,
    CurrencyInfo,
    Defaults,
    DisplayUnit
)

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

        # Get display unit from config or coordinator
        if hasattr(coordinator, 'display_unit') and coordinator.display_unit:
            self._display_unit = coordinator.display_unit
        else:
            self._display_unit = config_data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)

        # Determine if subunit conversion is needed
        self._use_subunit = self._display_unit == DisplayUnit.CENTS

        # Get currency from region
        self._currency = config_data.get(Attributes.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(self._area))

        # Create standardized entity_id
        self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{self._area.lower()}"

        # Create standardized name
        self._attr_name = f"GE-Spot {name_suffix} {self._area}"

        # Create standardized unique_id
        self._attr_unique_id = f"gespot_{sensor_type}_{self._area}".lower()

        # Set unit based on display_unit configuration
        # This only affects the display - actual conversion is done by the APIs
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

        # Base attributes
        attrs = {
            Attributes.CURRENCY: self._currency,
            Attributes.AREA: self._area,
            Attributes.VAT: f"{self._vat}%",  # Format VAT as percentage
            Attributes.LAST_UPDATED: self.coordinator.data.get(Attributes.LAST_UPDATED),
            "display_unit": self._display_unit,
            "use_subunit": self._use_subunit
        }

        # Add data_source from source_info - no duplication
        if "source_info" in self.coordinator.data:
            source_info = self.coordinator.data["source_info"]
            attrs[Attributes.DATA_SOURCE] = source_info.get("active_source")

        # Add exchange rate information if available - unified representation
        if "exchange_rate_info" in self.coordinator.data:
            exchange_info = self.coordinator.data.get("exchange_rate_info", {})
            if "rate" in exchange_info:
                attrs["exchange_rate"] = exchange_info["rate"]
            if "formatted" in exchange_info:
                attrs["exchange_rate_formatted"] = exchange_info["formatted"]
            if "timestamp" in exchange_info:
                attrs["exchange_rate_timestamp"] = exchange_info["timestamp"]

        # Add source_info but don't include duplicated attributes
        if "source_info" in self.coordinator.data:
            attrs["source_info"] = self.coordinator.data["source_info"]

        # Add raw value information if available
        if "raw_values" in self.coordinator.data and self._sensor_type in self.coordinator.data["raw_values"]:
            raw_info = self.coordinator.data["raw_values"][self._sensor_type]
            if isinstance(raw_info, dict):
                # Add raw currency and value
                if "raw" in raw_info:
                    attrs["raw_value"] = raw_info["raw"]
                if "unit" in raw_info:
                    attrs["raw_unit"] = raw_info["unit"]

        # Add next update time
        if "next_update" in self.coordinator.data:
            attrs["next_update"] = self.coordinator.data.get("next_update")

        return attrs

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()

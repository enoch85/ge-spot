"""Support for electricity price sensors."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceSensor(SensorEntity):
    """Sensor for electricity prices."""
    
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.MONETARY
    
    def __init__(self, coordinator, currency, area, vat, precision):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_name = f"Electricity Price {area}"
        self._attr_unique_id = f"electricity_price_{area}_{currency}".lower()
        self._attr_native_unit_of_measurement = f"{currency}/kWh"
        self._attr_suggested_display_precision = precision
        self._currency = currency
        self._area = area
        self._vat = vat
        
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["current_price"]
        
    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
            
        return {
            "currency": self._currency,
            "area": self._area,
            "vat": self._vat,
            "today": self.coordinator.data["today_prices"],
            "tomorrow": self.coordinator.data["tomorrow_prices"],
            "tomorrow_valid": self.coordinator.data["tomorrow_valid"],
            "raw_today": self.coordinator.data["today_raw"],
            "raw_tomorrow": self.coordinator.data["tomorrow_raw"],
            "current_price": self.coordinator.data["current_price"],
            "min": self.coordinator.data["today_stats"]["min"],
            "max": self.coordinator.data["today_stats"]["max"],
            "average": self.coordinator.data["today_stats"]["average"],
            "off_peak_1": self.coordinator.data["today_stats"]["off_peak_1"],
            "off_peak_2": self.coordinator.data["today_stats"]["off_peak_2"],
            "peak": self.coordinator.data["today_stats"]["peak"],
            "last_updated": self.coordinator.data["last_update"],
        }
        
    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        
    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[entry.domain][entry.entry_id]
    
    async_add_entities([
        ElectricityPriceSensor(
            coordinator,
            entry.data.get("currency"),
            entry.data.get("area"),
            entry.data.get("vat", 0),
            entry.data.get("precision", 3)
        )
    ])

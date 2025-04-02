"""Support for electricity price sensors."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)

from .const import (
    DOMAIN,
    ATTR_CURRENCY,
    ATTR_AREA,
    ATTR_VAT,
    ATTR_TODAY,
    ATTR_TOMORROW,
    ATTR_TOMORROW_VALID,
    ATTR_RAW_TODAY,
    ATTR_RAW_TOMORROW,
    ATTR_CURRENT_PRICE,
    ATTR_MIN,
    ATTR_MAX,
    ATTR_AVERAGE,
    ATTR_OFF_PEAK_1,
    ATTR_OFF_PEAK_2,
    ATTR_PEAK,
    ATTR_LAST_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceSensor(SensorEntity):
    """Sensor for electricity prices."""
    
    _attr_state_class = SensorStateClass.TOTAL
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
        return self.coordinator.data[ATTR_CURRENT_PRICE]
        
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
            ATTR_CURRENCY: self._currency,
            ATTR_AREA: self._area,
            ATTR_VAT: self._vat,
            ATTR_TODAY: self.coordinator.data[ATTR_TODAY],
            ATTR_TOMORROW: self.coordinator.data[ATTR_TOMORROW],
            ATTR_TOMORROW_VALID: self.coordinator.data[ATTR_TOMORROW_VALID],
            ATTR_RAW_TODAY: self.coordinator.data[ATTR_RAW_TODAY],
            ATTR_RAW_TOMORROW: self.coordinator.data[ATTR_RAW_TOMORROW],
            ATTR_CURRENT_PRICE: self.coordinator.data[ATTR_CURRENT_PRICE],
            ATTR_MIN: self.coordinator.data["today_stats"][ATTR_MIN],
            ATTR_MAX: self.coordinator.data["today_stats"][ATTR_MAX],
            ATTR_AVERAGE: self.coordinator.data["today_stats"][ATTR_AVERAGE],
            ATTR_OFF_PEAK_1: self.coordinator.data["today_stats"][ATTR_OFF_PEAK_1],
            ATTR_OFF_PEAK_2: self.coordinator.data["today_stats"][ATTR_OFF_PEAK_2],
            ATTR_PEAK: self.coordinator.data["today_stats"][ATTR_PEAK],
            ATTR_LAST_UPDATED: self.coordinator.data[ATTR_LAST_UPDATED],
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
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        ElectricityPriceSensor(
            coordinator,
            entry.data.get(ATTR_CURRENCY),
            entry.data.get(ATTR_AREA),
            entry.data.get(ATTR_VAT, 0),
            entry.data.get("precision", 3)
        )
    ])

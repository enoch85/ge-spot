"""Support for electricity price sensors."""
import logging
import datetime
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
    SENSOR_TYPE_CURRENT,
    SENSOR_TYPE_NEXT,
    SENSOR_TYPE_DAY_AVG,
    SENSOR_TYPE_PEAK,
    SENSOR_TYPE_OFF_PEAK,
    SENSOR_TYPE_TOMORROW_AVG,
    SENSOR_TYPE_TOMORROW_PEAK,
    SENSOR_TYPE_TOMORROW_OFF_PEAK,
    CONF_DISPLAY_UNIT,
    DEFAULT_DISPLAY_UNIT,
    DISPLAY_UNIT_CENTS,
    CURRENCY_SUBUNIT_NAMES,
)

_LOGGER = logging.getLogger(__name__)

class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""
    
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    
    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        self._currency = config_data.get(ATTR_CURRENCY)
        self._area = config_data.get(ATTR_AREA)
        self._vat = config_data.get(ATTR_VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type
        self._display_unit = config_data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)
        
        self._attr_name = f"Electricity {name_suffix} {self._area}"
        self._attr_unique_id = f"electricity_{sensor_type}_{self._area}_{self._currency}".lower()
        
        # Set the correct unit based on display_unit configuration
        if self._display_unit == DISPLAY_UNIT_CENTS:
            subunit = CURRENCY_SUBUNIT_NAMES.get(self._currency, "cents")
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
            
        return {
            ATTR_CURRENCY: self._currency,
            ATTR_AREA: self._area,
            ATTR_VAT: self._vat,
            ATTR_LAST_UPDATED: self.coordinator.data.get(ATTR_LAST_UPDATED),
        }
        
    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        
    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()


class CurrentPriceSensor(BaseElectricityPriceSensor):
    """Sensor for current electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the current price sensor."""
        super().__init__(coordinator, config_data, "current", "Current Price")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_CURRENT_PRICE)
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes
        if not self.coordinator.data:
            return attrs
            
        attrs.update({
            ATTR_TODAY: self.coordinator.data.get(ATTR_TODAY, []),
            ATTR_TOMORROW: self.coordinator.data.get(ATTR_TOMORROW, []),
            ATTR_TOMORROW_VALID: self.coordinator.data.get(ATTR_TOMORROW_VALID, False),
            ATTR_RAW_TODAY: self.coordinator.data.get(ATTR_RAW_TODAY, []),
            ATTR_RAW_TOMORROW: self.coordinator.data.get(ATTR_RAW_TOMORROW, []),
        })
        return attrs


class NextHourPriceSensor(BaseElectricityPriceSensor):
    """Sensor for next hour electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the next hour price sensor."""
        super().__init__(coordinator, config_data, "next_hour", "Next Hour Price")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data is None or "adapter" not in self.coordinator.data:
            return None
            
        # Use Home Assistant's dt_util to get the current time
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        
        adapter = self.coordinator.data["adapter"]
        return adapter.get_current_price(reference_time=next_hour)


class DayAveragePriceSensor(BaseElectricityPriceSensor):
    """Sensor for day average electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the day average price sensor."""
        super().__init__(coordinator, config_data, "day_average", "Day Average")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "today_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["today_stats"].get(ATTR_AVERAGE)


class PeakPriceSensor(BaseElectricityPriceSensor):
    """Sensor for peak electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the peak price sensor."""
        super().__init__(coordinator, config_data, "peak", "Peak Price")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "today_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["today_stats"].get(ATTR_MAX)


class OffPeakPriceSensor(BaseElectricityPriceSensor):
    """Sensor for off-peak electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the off-peak price sensor."""
        super().__init__(coordinator, config_data, "off_peak", "Off-Peak Price")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "today_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["today_stats"].get(ATTR_MIN)


class TomorrowAveragePriceSensor(BaseElectricityPriceSensor):
    """Sensor for tomorrow average electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow average price sensor."""
        super().__init__(coordinator, config_data, "tomorrow_average", "Tomorrow Average")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "tomorrow_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["tomorrow_stats"].get(ATTR_AVERAGE)


class TomorrowPeakPriceSensor(BaseElectricityPriceSensor):
    """Sensor for tomorrow peak electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow peak price sensor."""
        super().__init__(coordinator, config_data, "tomorrow_peak", "Tomorrow Peak")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "tomorrow_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["tomorrow_stats"].get(ATTR_MAX)


class TomorrowOffPeakPriceSensor(BaseElectricityPriceSensor):
    """Sensor for tomorrow off-peak electricity price."""
    
    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow off-peak price sensor."""
        super().__init__(coordinator, config_data, "tomorrow_off_peak", "Tomorrow Off-Peak")
    
    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "tomorrow_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["tomorrow_stats"].get(ATTR_MIN)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Create all sensor entities
    sensors = [
        CurrentPriceSensor(coordinator, entry.data),
        NextHourPriceSensor(coordinator, entry.data),
        DayAveragePriceSensor(coordinator, entry.data),
        PeakPriceSensor(coordinator, entry.data),
        OffPeakPriceSensor(coordinator, entry.data),
        TomorrowAveragePriceSensor(coordinator, entry.data),
        TomorrowPeakPriceSensor(coordinator, entry.data),
        TomorrowOffPeakPriceSensor(coordinator, entry.data),
    ]
    
    async_add_entities(sensors)

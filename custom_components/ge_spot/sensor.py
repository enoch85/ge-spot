import logging
from typing import Optional
import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_AREA,
    CONF_DISPLAY_UNIT,
    DISPLAY_UNIT_CENTS,
    SENSOR_TYPE_CURRENT,
    SENSOR_TYPE_NEXT,
    SENSOR_TYPE_DAY_AVG,
    SENSOR_TYPE_PEAK,
    SENSOR_TYPE_OFF_PEAK,
    SENSOR_TYPE_TOMORROW_AVG,
    SENSOR_TYPE_TOMORROW_PEAK,
    SENSOR_TYPE_TOMORROW_OFF_PEAK,
    CURRENCY_BY_SOURCE,
    CURRENCY_SUBUNITS,
    DEFAULT_DISPLAY_UNIT,
    GENERIC_SENSOR_NAMES,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the energy price sensors from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    source = entry.data.get(CONF_SOURCE)
    area = entry.data.get(CONF_AREA)
    
    # Get display unit preference
    display_unit = entry.options.get(
        CONF_DISPLAY_UNIT,
        entry.data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)
    )
    
    # Determine currency based on source and area
    if isinstance(CURRENCY_BY_SOURCE[source], dict):
        currency = CURRENCY_BY_SOURCE[source].get(area, "EUR")
    else:
        currency = CURRENCY_BY_SOURCE[source]
    
    # Create sensors
    sensors = []
    
    # Source-specific sensors with standard names
    sensors.extend([
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_CURRENT,
            currency,
            f"{source.title()} Current Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_NEXT,
            currency,
            f"{source.title()} Next Hour Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_DAY_AVG,
            currency,
            f"{source.title()} Day Average Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_PEAK,
            currency,
            f"{source.title()} Peak Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_OFF_PEAK,
            currency,
            f"{source.title()} Off-Peak Price",
            display_unit,
            False,  # is_generic
        ),
        # Add tomorrow's sensors
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_AVG,
            currency,
            f"{source.title()} Tomorrow Average Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_PEAK,
            currency,
            f"{source.title()} Tomorrow Peak Price",
            display_unit,
            False,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_OFF_PEAK,
            currency,
            f"{source.title()} Tomorrow Off-Peak Price",
            display_unit,
            False,  # is_generic
        ),
    ])
    
    # Generic sensors that are source-agnostic
    sensors.extend([
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_CURRENT,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_CURRENT],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_NEXT,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_NEXT],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_DAY_AVG,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_DAY_AVG],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_PEAK,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_PEAK],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_OFF_PEAK,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_OFF_PEAK],
            display_unit,
            True,  # is_generic
        ),
        # Add tomorrow's generic sensors
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_AVG,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_TOMORROW_AVG],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_PEAK,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_TOMORROW_PEAK],
            display_unit,
            True,  # is_generic
        ),
        GSpotSensor(
            coordinator,
            entry,
            SENSOR_TYPE_TOMORROW_OFF_PEAK,
            currency,
            GENERIC_SENSOR_NAMES[SENSOR_TYPE_TOMORROW_OFF_PEAK],
            display_unit,
            True,  # is_generic
        ),
    ])
    
    async_add_entities(sensors)

class GSpotSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Energy Price Sensor."""

    def __init__(self, coordinator, entry, sensor_type, currency, name, display_unit, is_generic=False):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._source = entry.data.get(CONF_SOURCE)
        self._area = entry.data.get(CONF_AREA)
        self._currency = currency
        self._display_unit = display_unit
        self._is_generic = is_generic
        
        # Set unit of measurement based on display preference
        if display_unit == DISPLAY_UNIT_CENTS:
            subunit = CURRENCY_SUBUNITS.get(currency, "cents")
            self._attr_native_unit_of_measurement = f"{subunit}/kWh"
        else:
            self._attr_native_unit_of_measurement = f"{currency}/kWh"
            
        self._attr_device_class = SensorDeviceClass.MONETARY
        
        # For monetary sensors, the state class should be measurement, not total
        self._attr_state_class = SensorStateClass.MEASUREMENT
        
        self._attr_has_entity_name = False
        self._attr_name = name
        
        # Generate unique ID - use generic ID for generic sensors
        if is_generic:
            # Strip 'price' from the end for a cleaner entity_id
            sensor_type_clean = sensor_type.replace("_price", "")
            self._attr_unique_id = f"{DOMAIN}_electricity_{sensor_type_clean}"
        else:
            self._attr_unique_id = f"{DOMAIN}_{self._source}_{self._area}_{sensor_type}"
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        
        # Check if we have the specific data this sensor needs
        if not self.coordinator.data:
            return False
            
        # Check for the specific sensor type in the data
        if self._sensor_type in self.coordinator.data:
            return self.coordinator.data[self._sensor_type] is not None
        
        return False
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        # Get the raw value
        raw_value = self.coordinator.data.get(self._sensor_type)
        
        if raw_value is None:
            return None
            
        # Convert to cents/öre if needed
        if self._display_unit == DISPLAY_UNIT_CENTS:
            return round(raw_value * 100, 1)  # Convert to cents/öre and round to 1 decimal
        
        return raw_value  # Keep as decimal
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
            
        attrs = {
            "source": self._source,
            "area": self._area,
            "last_updated": self.coordinator.data.get("last_updated"),
            "display_unit": self._display_unit,
            "currency": self._currency,
        }
        
        # Indicate if this is simulated data
        if self.coordinator.data.get("simulated", False):
            attrs["simulated"] = True
            
        # Indicate if this is from fallback
        if self.coordinator.data.get("from_fallback", False):
            attrs["from_fallback"] = True
            attrs["fallback_source"] = self.coordinator.data.get("fallback_source")
            
        # Indicate if this is from cache
        if self.coordinator.data.get("from_cache", False):
            attrs["from_cache"] = True
        
        # Add all prices for the day for the current price sensor only
        if self._sensor_type == SENSOR_TYPE_CURRENT and "hourly_prices" in self.coordinator.data:
            for hour, price in self.coordinator.data["hourly_prices"].items():
                # Convert price if using cents/öre display
                if self._display_unit == DISPLAY_UNIT_CENTS:
                    price = round(price * 100, 1)
                attrs[f"price_{hour}"] = price
                
        # Add all prices for tomorrow for the tomorrow average sensor only
        if self._sensor_type == SENSOR_TYPE_TOMORROW_AVG and "tomorrow_hourly_prices" in self.coordinator.data:
            for hour, price in self.coordinator.data["tomorrow_hourly_prices"].items():
                # Convert price if using cents/öre display
                if self._display_unit == DISPLAY_UNIT_CENTS:
                    price = round(price * 100, 1)
                attrs[f"tomorrow_price_{hour}"] = price
                
        return attrs

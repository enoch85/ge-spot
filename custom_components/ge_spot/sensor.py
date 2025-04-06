"""Support for electricity price sensors."""
import logging
import datetime
from typing import Any, Dict, Optional, List, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ATTR_CURRENCY, ATTR_AREA, ATTR_VAT, ATTR_LAST_UPDATED,
    ATTR_DATA_SOURCE, ATTR_FALLBACK_USED, ATTR_IS_USING_FALLBACK,
    ATTR_AVAILABLE_FALLBACKS, ATTR_MIN, ATTR_MAX,
    ATTR_TODAY, ATTR_TOMORROW, ATTR_TOMORROW_VALID,
    ATTR_API_KEY_STATUS,
    CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT, DISPLAY_UNIT_CENTS,
    CURRENCY_SUBUNIT_NAMES, REGION_TO_CURRENCY,
    SOURCE_ENTSO_E,
)

_LOGGER = logging.getLogger(__name__)

class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        self._area = config_data.get(ATTR_AREA)
        self._vat = config_data.get(ATTR_VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type
        self._display_unit = config_data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)

        # Get currency from region
        self._currency = config_data.get(ATTR_CURRENCY, REGION_TO_CURRENCY.get(self._area))

        # Create standardized entity_id
        self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{self._area.lower()}"

        # Create standardized name
        self._attr_name = f"GE-Spot {name_suffix} {self._area}"

        # Create standardized unique_id
        self._attr_unique_id = f"gespot_{sensor_type}_{self._area}".lower()

        # Set unit based on display_unit configuration
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

        attrs = {
            ATTR_CURRENCY: self._currency,
            ATTR_AREA: self._area,
            ATTR_VAT: self._vat,
            ATTR_LAST_UPDATED: self.coordinator.data.get(ATTR_LAST_UPDATED),
            ATTR_DATA_SOURCE: self.coordinator.data.get(ATTR_DATA_SOURCE),
            "is_using_fallback": self.coordinator.data.get(ATTR_IS_USING_FALLBACK, False),
        }

        # Add exchange rate information if available
        if "raw_values" in self.coordinator.data and "current_price" in self.coordinator.data["raw_values"]:
            raw_price_info = self.coordinator.data["raw_values"]["current_price"]
            if isinstance(raw_price_info, dict):
                # Add raw currency
                if "unit" in raw_price_info:
                    attrs["current_raw_currency"] = raw_price_info["unit"]
                # Add exchange rate used
                if "exchange_rate" in raw_price_info:
                    attrs["current_exchange_rate"] = raw_price_info["exchange_rate"]

        # Add source information if available
        if "source_info" in self.coordinator.data:
            attrs["source_info"] = self.coordinator.data["source_info"]

        # Add available fallbacks information
        if ATTR_AVAILABLE_FALLBACKS in self.coordinator.data:
            attrs["available_fallbacks"] = self.coordinator.data[ATTR_AVAILABLE_FALLBACKS]

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


class PriceValueSensor(BaseElectricityPriceSensor):
    """Generic sensor for price values with flexible data extraction."""

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, value_fn, additional_attrs=None):
        """Initialize the price value sensor.

        Args:
            coordinator: The data coordinator
            config_data: Configuration data
            sensor_type: Type of sensor (used for entity ID)
            name_suffix: Suffix for the entity name
            value_fn: Function to extract the sensor value from coordinator data
            additional_attrs: Function to get additional attributes (optional)
        """
        super().__init__(coordinator, config_data, sensor_type, name_suffix)
        self._value_fn = value_fn
        self._additional_attrs = additional_attrs

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None
        return self._value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        # Add additional attributes if function provided
        if self._additional_attrs and self.coordinator.data:
            additional = self._additional_attrs(self.coordinator.data)
            if additional:
                attrs.update(additional)

        return attrs


class TomorrowSensorMixin:
    """Mixin to provide tomorrow-specific behavior."""

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
        # Only available if tomorrow data is valid
        return self.coordinator.data.get(ATTR_TOMORROW_VALID, False)


class TimestampAttributeMixin:
    """Mixin to provide timestamp attribute."""

    def __init__(self, *args, timestamp_key=None, **kwargs):
        """Initialize with timestamp key."""
        super().__init__(*args, **kwargs)
        self._timestamp_key = timestamp_key or f"{self._extrema_type}_timestamp"

    def get_additional_attrs(self, data):
        """Get additional attributes including timestamp."""
        attrs = {}
        stats_key = self._stats_key

        if stats_key in data and self._timestamp_key in data[stats_key]:
            attrs["timestamp"] = data[stats_key][self._timestamp_key]

        return attrs


class ExtremaPriceSensor(PriceValueSensor, TimestampAttributeMixin):
    """Base class for min/max price sensors."""

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, day_offset=0, extrema_type="min"):
        """Initialize the extrema price sensor."""
        self._day_offset = day_offset  # 0 for today, 1 for tomorrow
        self._extrema_type = extrema_type  # "min" or "max"
        self._stats_key = "today_stats" if day_offset == 0 else "tomorrow_stats"

        # Create value extraction function
        def extract_value(data):
            if self._stats_key not in data:
                return None

            # Get min or max based on extrema_type
            attr_key = "min" if self._extrema_type == "min" else "max"
            const_attr = ATTR_MIN if self._extrema_type == "min" else ATTR_MAX

            return data[self._stats_key].get(attr_key) or data[self._stats_key].get(const_attr)

        # Initialize with value function and timestamp attribute getter
        super().__init__(
            coordinator,
            config_data,
            sensor_type,
            name_suffix,
            extract_value,
            self.get_additional_attrs
        )


# Create a proper combined class for tomorrow extrema sensors
class TomorrowExtremaPriceSensor(TomorrowSensorMixin, ExtremaPriceSensor):
    """Extrema price sensor for tomorrow data with proper availability behavior."""
    pass


# Create a proper combined class for tomorrow average sensor
class TomorrowAveragePriceSensor(TomorrowSensorMixin, PriceValueSensor):
    """Average price sensor for tomorrow data with proper availability behavior."""
    pass


def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the electricity price sensors from config entries."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    area = config_entry.data.get(ATTR_AREA)
    vat = config_entry.data.get(ATTR_VAT, 0)

    # Determine currency based on area
    currency = config_entry.data.get(ATTR_CURRENCY, REGION_TO_CURRENCY.get(area))

    config_data = {
        ATTR_AREA: area,
        ATTR_VAT: vat,
        ATTR_CURRENCY: currency,
        CONF_DISPLAY_UNIT: config_entry.options.get(
            CONF_DISPLAY_UNIT,
            config_entry.data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)
        ),
    }

    # Define sensors with their value extraction functions
    sensor_definitions = [
        # Current price sensor (with additional today/tomorrow data)
        {
            "type": "current_price",
            "name": "Current Price",
            "class": PriceValueSensor,
            "value_fn": lambda data: data.get("current_price"),
            "additional_attrs": lambda data: {
                ATTR_TODAY: data.get(ATTR_TODAY, []),
                ATTR_TOMORROW: data.get(ATTR_TOMORROW, []),
                ATTR_TOMORROW_VALID: data.get(ATTR_TOMORROW_VALID, False),
                "exchange_service_timestamp": data.get("exchange_rate_info", {}).get("timestamp"),
                "exchange_service_rate": data.get("exchange_rate_info", {}).get("formatted"),
                "entso_e_api_key": data.get(ATTR_API_KEY_STATUS, {}).get(SOURCE_ENTSO_E, {})
            }
        },
        # Next hour price
        {
            "type": "next_hour_price",
            "name": "Next Hour Price",
            "class": PriceValueSensor,
            "value_fn": lambda data: data["adapter"].get_current_price(
                reference_time=dt_util.now().replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
            ) if "adapter" in data else None
        },
        # Day average
        {
            "type": "day_average_price",
            "name": "Day Average",
            "class": PriceValueSensor,
            "value_fn": lambda data: data.get("today_stats", {}).get("average")
        },
        # Today peak price (max)
        {
            "type": "peak_price",
            "name": "Peak Price",
            "class": ExtremaPriceSensor,
            "kwargs": {"day_offset": 0, "extrema_type": "max"}
        },
        # Today off-peak price (min)
        {
            "type": "off_peak_price",
            "name": "Off-Peak Price",
            "class": ExtremaPriceSensor,
            "kwargs": {"day_offset": 0, "extrema_type": "min"}
        },
        # Tomorrow average price
        {
            "type": "tomorrow_average_price",
            "name": "Tomorrow Average",
            "class": TomorrowAveragePriceSensor,
            "value_fn": lambda data: data.get("tomorrow_stats", {}).get("average")
        },
        # Tomorrow peak price (max)
        {
            "type": "tomorrow_peak_price",
            "name": "Tomorrow Peak",
            "class": TomorrowExtremaPriceSensor,
            "kwargs": {"day_offset": 1, "extrema_type": "max"}
        },
        # Tomorrow off-peak price (min)
        {
            "type": "tomorrow_off_peak_price",
            "name": "Tomorrow Off-Peak",
            "class": TomorrowExtremaPriceSensor,
            "kwargs": {"day_offset": 1, "extrema_type": "min"}
        }
    ]

    entities = []

    # Create sensor entities based on definitions
    for sensor_def in sensor_definitions:
        sensor_class = sensor_def["class"]

        if sensor_class == PriceValueSensor:
            entities.append(PriceValueSensor(
                coordinator,
                config_data,
                sensor_def["type"],
                sensor_def["name"],
                sensor_def["value_fn"],
                sensor_def.get("additional_attrs")
            ))
        elif sensor_class == TomorrowAveragePriceSensor:
            entities.append(TomorrowAveragePriceSensor(
                coordinator,
                config_data,
                sensor_def["type"],
                sensor_def["name"],
                sensor_def["value_fn"],
                sensor_def.get("additional_attrs")
            ))
        else:
            # For ExtremaPriceSensor and TomorrowExtremaPriceSensor
            entities.append(sensor_class(
                coordinator,
                config_data,
                sensor_def["type"],
                sensor_def["name"],
                **sensor_def.get("kwargs", {})
            ))

    async_add_entities(entities)

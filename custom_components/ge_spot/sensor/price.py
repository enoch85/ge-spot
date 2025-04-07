"""Price-specific sensor implementations."""
import logging
import datetime
from typing import Any, Dict, Optional, Callable

from homeassistant.util import dt as dt_util

from .base import BaseElectricityPriceSensor
from ..const import ATTR_TODAY, ATTR_TOMORROW, ATTR_TOMORROW_VALID, ATTR_MIN, ATTR_MAX, ATTR_API_KEY_STATUS, SOURCE_ENTSO_E

_LOGGER = logging.getLogger(__name__)

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
        
        # Get the raw value using the provided extraction function
        value = self._value_fn(self.coordinator.data)
        
        # No need to apply any conversion - values from coordinator should already be 
        # properly converted by the API with correct currency and subunit format
        return value

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


class TimestampAttributeMixin:
    """Mixin to provide timestamp attribute."""

    def get_additional_attrs(self, data):
        """Get additional attributes including timestamp."""
        attrs = {}

        # Check for required attributes
        if not hasattr(self, '_stats_key') or not hasattr(self, '_extrema_type'):
            return attrs

        stats_key = self._stats_key
        timestamp_key = f"{self._extrema_type}_timestamp"

        if data and stats_key in data and timestamp_key in data.get(stats_key, {}):
            attrs["timestamp"] = data[stats_key][timestamp_key]

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

        # Initialize parent classes
        PriceValueSensor.__init__(
            self,
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

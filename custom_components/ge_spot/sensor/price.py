"""Price-specific sensor implementations."""
import logging
from typing import Any, Dict, Optional, Callable
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.util import dt as dt_util

from .base import BaseElectricityPriceSensor

_LOGGER = logging.getLogger(__name__)

class PriceValueSensor(BaseElectricityPriceSensor):
    """Representation of a GE Spot price sensor."""

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        value_fn: Callable[[Dict[str, Any]], Optional[float]], # Added parameter
        additional_attrs: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None # Added parameter
    ):
        """Initialize the sensor."""
        # Ensure config_data is a dictionary before passing to super().__init__
        if not isinstance(config_data, dict):
            config_data = {"entry_id": coordinator.config_entry.entry_id}

        super().__init__(coordinator, config_data, sensor_type, name_suffix)
        self._value_fn = value_fn
        self._additional_attrs = additional_attrs

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        # Return the value directly from the coordinator data via the value function.
        # The DataProcessor/CurrencyConverter already handles subunit conversion.
        value = self._value_fn(self.coordinator.data)

        return value

    def _format_timestamp_display(self, timestamp_prices):
        """Format timestamp prices for clean display in attributes."""
        formatted = {}

        for timestamp_str, price in timestamp_prices.items():
            try:
                # Parse timestamp
                dt = datetime.fromisoformat(timestamp_str)
                # Format using HA's datetime display format directly
                formatted_time = dt_util.as_local(dt).isoformat(timespec='minutes')

                # Format price with 2 decimal places
                if isinstance(price, (int, float)):
                    formatted_price = round(price, 2)
                else:
                    formatted_price = price

                # Add to formatted dict with price
                formatted[formatted_time] = formatted_price
            except (ValueError, TypeError):
                formatted[timestamp_str] = price

        return formatted

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        # Add formatted timestamps with prices for current price sensor
        if self._sensor_type == "current_price" and self.coordinator.data:
            # Use processed interval prices from coordinator data
            today_prices = self.coordinator.data.get("interval_prices")
            if today_prices:
                attrs["today_with_timestamps"] = self._format_timestamp_display(today_prices)

            # Add tomorrow prices if valid and available
            if self.coordinator.data.get("tomorrow_valid", False):
                tomorrow_prices = self.coordinator.data.get("tomorrow_interval_prices")
                if tomorrow_prices:
                    attrs["tomorrow_with_timestamps"] = self._format_timestamp_display(tomorrow_prices)

        # Add additional attributes if provided
        if self._additional_attrs and self.coordinator.data:
            additional = self._additional_attrs(self.coordinator.data)
            if additional:
                # Keep only essential additional attributes
                essential_attrs = {}
                for key, value in additional.items():
                    if key == "tomorrow_valid":
                        essential_attrs[key] = value
                attrs.update(essential_attrs)

        return attrs


class ExtremaPriceSensor(PriceValueSensor):
    """Base class for min/max price sensors."""

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, day_offset=0, extrema_type="min"):
        """Initialize the extrema price sensor."""
        self._day_offset = day_offset
        self._extrema_type = extrema_type
        # Use the correct keys used by DataProcessor
        self._stats_key = "statistics" if day_offset == 0 else "tomorrow_statistics"

        # Create value extraction function
        def extract_value(data):
            if self._stats_key not in data or not data[self._stats_key]: # Check if stats dict exists and is not empty
                 _LOGGER.debug(f"Stats key '{self._stats_key}' not found or empty in data for {self.entity_id}")
                 return None
            stats_dict = data[self._stats_key]
            key = "min" if self._extrema_type == "min" else "max"
            value = stats_dict.get(key)
            # Add specific logging for this sensor type
            _LOGGER.debug(f"ExtremaSensor {self.entity_id}: Reading '{key}' from '{self._stats_key}'. Found value: {value}. Stats dict: {stats_dict}")
            return value

        def get_timestamp(data):
            from homeassistant.util import dt as dt_util
            stats = data.get(self._stats_key, {}) # Use .get() for safety
            timestamp_key = f"{self._extrema_type}_timestamp"
            price_key = "min" if self._extrema_type == "min" else "max"
            price_value = stats.get(price_key)

            # Format the price value
            if isinstance(price_value, (int, float)):
                price_value = round(price_value, 2)

            if timestamp_key in stats:
                timestamp = stats[timestamp_key]
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        # Use HA's datetime format
                        formatted_time = dt_util.as_local(dt).isoformat(timespec='minutes')
                        return {"timestamp": formatted_time, "value": price_value}
                    except (ValueError, TypeError):
                        return {"timestamp": timestamp, "value": price_value}
                return {"timestamp": timestamp, "value": price_value}
            return {}

        # Initialize parent class
        super().__init__(
            coordinator,
            config_data,
            sensor_type,
            name_suffix,
            extract_value,
            get_timestamp
        )


class TomorrowSensorMixin:
    """Mixin to provide tomorrow-specific behavior."""

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
        # Only available if tomorrow data is valid
        return self.coordinator.data.get("tomorrow_valid", False)


class TomorrowExtremaPriceSensor(TomorrowSensorMixin, ExtremaPriceSensor):
    """Extrema price sensor for tomorrow data with proper availability behavior."""
    pass


class TomorrowAveragePriceSensor(TomorrowSensorMixin, PriceValueSensor):
    """Average price sensor for tomorrow data with proper availability behavior."""
    pass


class PriceStatisticSensor(PriceValueSensor):
    """Sensor for price statistics (average, min, max)."""
    device_class    = SensorDeviceClass.MONETARY
    state_class     = SensorStateClass.TOTAL  # Changed from MEASUREMENT to TOTAL for HA compliance

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, stat_type):
        """Initialize the price statistic sensor."""
        # Create value extraction function
        def extract_value(data):
            # Use .get() for safety and the correct key "statistics"
            stats = data.get("statistics", {})
            if not stats:
                _LOGGER.debug(f"PriceStatisticSensor {self.entity_id}: 'statistics' dictionary not found or empty in data.")
                return None
            value = stats.get(stat_type)
            _LOGGER.debug(f"PriceStatisticSensor {self.entity_id}: Reading '{stat_type}' from 'statistics'. Found value: {value}. Stats dict: {stats}")
            return value

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data, # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None
        )
        self._stat_type = stat_type

    # Add this property to inherit unit logic from base class
    @property
    def native_unit_of_measurement(self):
        return super().native_unit_of_measurement


class PriceDifferenceSensor(PriceValueSensor):
    """Sensor for price difference between two values."""
    device_class    = SensorDeviceClass.MONETARY
    state_class     = SensorStateClass.TOTAL  # Changed from MEASUREMENT to TOTAL for HA compliance

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, value1_key, value2_key):
        """Initialize the price difference sensor."""
        # Create value extraction function
        def extract_value(data):
            value1 = data.get(value1_key)
            if value1_key == "current_price" and value1 is None:
                # Try to get from statistics
                stats = data.get("statistics", {})
                value1 = stats.get("current") # Assuming 'current' might exist in stats, otherwise this needs adjustment
                _LOGGER.debug(f"PriceDifferenceSensor {self.entity_id}: Fallback for current_price from statistics: {value1}")

            value2 = None
            if value2_key == "average":
                # Get from statistics
                stats = data.get("statistics", {})
                value2 = stats.get("avg")  # Fixed: use 'avg' to match PriceStatistics dataclass
                _LOGGER.debug(f"PriceDifferenceSensor {self.entity_id}: Reading average from statistics: {value2}")
            else:
                value2 = data.get(value2_key)
                _LOGGER.debug(f"PriceDifferenceSensor {self.entity_id}: Reading {value2_key} directly: {value2}")

            if value1 is None or value2 is None:
                _LOGGER.debug(f"PriceDifferenceSensor {self.entity_id}: Calculation failed. value1={value1}, value2={value2}")
                return None

            result = value1 - value2
            _LOGGER.debug(f"PriceDifferenceSensor {self.entity_id}: Calculated difference: {result} (value1={value1}, value2={value2})")
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data, # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None
        )
        self._value1_key = value1_key
        self._value2_key = value2_key


class PricePercentSensor(PriceValueSensor):
    """Sensor for price percentage relative to a reference value."""
    device_class    = SensorDeviceClass.MONETARY
    state_class     = None  # Percent is not a monetary total, so set to None

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, value_key, reference_key):
        """Initialize the price percentage sensor."""
        # Create value extraction function
        def extract_value(data):
            value = data.get(value_key)
            if value_key == "current_price" and value is None:
                # Try to get from statistics
                stats = data.get("statistics", {})
                value = stats.get("current") # Assuming 'current' might exist in stats
                _LOGGER.debug(f"PricePercentSensor {self.entity_id}: Fallback for current_price from statistics: {value}")

            reference = None
            if reference_key == "average":
                # Get from statistics
                stats = data.get("statistics", {})
                reference = stats.get("avg")  # Fixed: use 'avg' to match PriceStatistics dataclass
                _LOGGER.debug(f"PricePercentSensor {self.entity_id}: Reading average from statistics: {reference}")
            else:
                reference = data.get(reference_key)
                _LOGGER.debug(f"PricePercentSensor {self.entity_id}: Reading {reference_key} directly: {reference}")

            if value is None or reference is None or reference == 0:
                _LOGGER.debug(f"PricePercentSensor {self.entity_id}: Calculation failed. value={value}, reference={reference}")
                return None

            result = (value / reference - 1) * 100
            _LOGGER.debug(f"PricePercentSensor {self.entity_id}: Calculated percentage: {result} (value={value}, reference={reference})")
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data, # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None
        )
        self._value_key = value_key
        self._reference_key = reference_key

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

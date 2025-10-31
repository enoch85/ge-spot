"""Price-specific sensor implementations."""

import logging
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass
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
        value_fn: Callable[[Dict[str, Any]], Optional[float]],  # Added parameter
        additional_attrs: Optional[
            Callable[[Dict[str, Any]], Dict[str, Any]]
        ] = None,  # Added parameter
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
                formatted_time = dt_util.as_local(dt).isoformat(timespec="minutes")

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

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        day_offset=0,
        extrema_type="min",
    ):
        """Initialize the extrema price sensor."""
        self._day_offset = day_offset
        self._extrema_type = extrema_type

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(f"ExtremaSensor {self.entity_id}: No data available")
                return None

            # data is IntervalPriceData object - use properties
            stats = data.statistics if day_offset == 0 else data.tomorrow_statistics
            if not stats:
                _LOGGER.debug(
                    f"ExtremaSensor {self.entity_id}: statistics not available for day_offset={day_offset}"
                )
                return None

            # stats is PriceStatistics object - access as attribute
            value = stats.min if extrema_type == "min" else stats.max
            _LOGGER.debug(
                f"ExtremaSensor {self.entity_id}: Reading '{extrema_type}' from statistics. Found value: {value}."
            )
            return value

        def get_timestamp(data):
            if not data:
                return {}

            # data is IntervalPriceData object - use properties
            stats = data.statistics if day_offset == 0 else data.tomorrow_statistics
            if not stats:
                return {}

            # Get timestamp and price from PriceStatistics object
            timestamp = (
                stats.min_timestamp if extrema_type == "min" else stats.max_timestamp
            )
            price_value = stats.min if extrema_type == "min" else stats.max

            # Format the price value
            if isinstance(price_value, (int, float)):
                price_value = round(price_value, 2)

            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    # Use HA's datetime format
                    formatted_time = dt_util.as_local(dt).isoformat(timespec="minutes")
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
            get_timestamp,
        )


class TomorrowSensorMixin:
    """Mixin to provide tomorrow-specific behavior."""

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
        # Only available if tomorrow data is valid (computed property)
        return self.coordinator.data.tomorrow_valid if self.coordinator.data else False


class TomorrowExtremaPriceSensor(TomorrowSensorMixin, ExtremaPriceSensor):
    """Extrema price sensor for tomorrow data with proper availability behavior."""

    pass


class TomorrowAveragePriceSensor(TomorrowSensorMixin, PriceValueSensor):
    """Average price sensor for tomorrow data with proper availability behavior."""

    pass


class PriceStatisticSensor(PriceValueSensor):
    """Sensor for price statistics (average, min, max)."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, stat_type):
        """Initialize the price statistic sensor."""

        # Create value extraction function
        def extract_value(data):
            # data is IntervalPriceData object, not dict - use properties
            if not data:
                _LOGGER.debug(
                    f"PriceStatisticSensor {self.entity_id}: No data available."
                )
                return None

            stats = data.statistics
            if not stats:
                _LOGGER.debug(
                    f"PriceStatisticSensor {self.entity_id}: statistics property returned empty."
                )
                return None

            # stats is PriceStatistics object - access as attribute
            value = getattr(stats, stat_type, None)
            _LOGGER.debug(
                f"PriceStatisticSensor {self.entity_id}: Reading '{stat_type}' from statistics. Found value: {value}."
            )
            return value

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._stat_type = stat_type

    # Add this property to inherit unit logic from base class
    @property
    def native_unit_of_measurement(self):
        return super().native_unit_of_measurement


class PriceDifferenceSensor(PriceValueSensor):
    """Sensor for price difference between two values."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    def __init__(
        self, coordinator, config_data, sensor_type, name_suffix, value1_key, value2_key
    ):
        """Initialize the price difference sensor."""

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: No data available."
                )
                return None

            # data is IntervalPriceData object - use properties
            value1 = None
            if value1_key == "current_price":
                value1 = data.current_price
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: current_price from property: {value1}"
                )
            else:
                # Try to get as property
                value1 = getattr(data, value1_key, None)
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: {value1_key} from property: {value1}"
                )

            value2 = None
            if value2_key == "average":
                # Get from statistics property
                stats = data.statistics
                value2 = stats.avg if stats else None
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Reading average from statistics: {value2}"
                )
            else:
                value2 = getattr(data, value2_key, None)
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Reading {value2_key} as property: {value2}"
                )

            if value1 is None or value2 is None:
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Calculation failed. value1={value1}, value2={value2}"
                )
                return None

            result = value1 - value2
            _LOGGER.debug(
                f"PriceDifferenceSensor {self.entity_id}: Calculated difference: {result} (value1={value1}, value2={value2})"
            )
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._value1_key = value1_key
        self._value2_key = value2_key


class PricePercentSensor(PriceValueSensor):
    """Sensor for price percentage relative to a reference value."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        value_key,
        reference_key,
    ):
        """Initialize the price percentage sensor."""

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: No data available."
                )
                return None

            # data is IntervalPriceData object - use properties
            value = None
            if value_key == "current_price":
                value = data.current_price
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: current_price from property: {value}"
                )
            else:
                value = getattr(data, value_key, None)
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: {value_key} from property: {value}"
                )

            reference = None
            if reference_key == "average":
                # Get from statistics property
                stats = data.statistics
                reference = stats.avg if stats else None
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Reading average from statistics: {reference}"
                )
            else:
                reference = getattr(data, reference_key, None)
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Reading {reference_key} as property: {reference}"
                )

            if value is None or reference is None or reference == 0:
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Calculation failed. value={value}, reference={reference}"
                )
                return None

            result = (value / reference - 1) * 100
            _LOGGER.debug(
                f"PricePercentSensor {self.entity_id}: Calculated percentage: {result} (value={value}, reference={reference})"
            )
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._value_key = value_key
        self._reference_key = reference_key

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"


class HourlyAverageSensor(PriceValueSensor):
    """Sensor that calculates hourly average prices from 15-minute intervals."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    # Override to exclude hourly price arrays from database (like interval prices)
    _unrecorded_attributes = frozenset(
        {
            "today_hourly_prices",
            "tomorrow_hourly_prices",
        }
    )

    def __init__(
        self, coordinator, config_data, sensor_type, name_suffix, day_offset=0
    ):
        """Initialize the hourly average price sensor.

        Args:
            coordinator: Data coordinator
            config_data: Configuration data
            sensor_type: Type identifier for the sensor
            name_suffix: Display name suffix
            day_offset: 0 for today, 1 for tomorrow
        """
        self._day_offset = day_offset

        # Create value extraction function
        def extract_value(data):
            """Extract current hour's average price."""
            hourly_prices = self._calculate_hourly_averages(data)
            if not hourly_prices:
                return None

            # Get current hour (or first hour of tomorrow for tomorrow sensor)
            if self._day_offset == 0:
                # For today: get current hour
                now = dt_util.now()
                current_hour = f"{now.hour:02d}:00"
                return hourly_prices.get(current_hour)
            else:
                # For tomorrow: return first hour's average
                sorted_hours = sorted(hourly_prices.keys())
                if sorted_hours:
                    return hourly_prices[sorted_hours[0]]
                return None

        # Create additional attributes function (not used, we override extra_state_attributes)
        def get_hourly_attrs(data):
            """Get hourly price attributes."""
            return {}

        # Initialize parent class
        super().__init__(
            coordinator,
            config_data,
            sensor_type,
            name_suffix,
            extract_value,
            get_hourly_attrs,
        )

    def _calculate_hourly_averages(self, data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate hourly averages from 15-minute interval prices.

        Args:
            data: Coordinator data containing interval prices

        Returns:
            Dictionary mapping hour (HH:00) to average price
        """
        # Get the appropriate interval prices based on day offset
        if self._day_offset == 0:
            interval_prices = data.today_interval_prices if data else {}
        else:
            interval_prices = data.tomorrow_interval_prices if data else {}

        if not interval_prices:
            return {}

        # Group intervals by hour and calculate averages
        hourly_data = {}
        for interval_key, price in interval_prices.items():
            try:
                # Extract hour from HH:MM format
                hour = interval_key.split(":")[0]
                hour_key = f"{hour}:00"

                # Initialize list for this hour if needed
                if hour_key not in hourly_data:
                    hourly_data[hour_key] = []

                # Add price to this hour's list
                hourly_data[hour_key].append(float(price))
            except (ValueError, AttributeError) as e:
                _LOGGER.warning(f"Failed to process interval {interval_key}: {e}")
                continue

        # Calculate averages
        hourly_averages = {}
        for hour_key, prices in hourly_data.items():
            if prices:
                hourly_averages[hour_key] = sum(prices) / len(prices)

        return hourly_averages

    def _convert_hourly_to_list(
        self, hourly_prices: Dict[str, float], base_date
    ) -> list:
        """Convert hourly prices dict to list format with datetime objects.

        Args:
            hourly_prices: Dictionary mapping hour (HH:00) to price
            base_date: Date to use for datetime objects

        Returns:
            List of dicts with 'time' (datetime) and 'value' (float) keys
        """
        # Get target timezone
        target_tz = dt_util.get_default_time_zone()

        hourly_list = []
        for hhmm_key in sorted(hourly_prices.keys()):
            try:
                hour = int(hhmm_key.split(":")[0])
                dt_obj = datetime(
                    base_date.year,
                    base_date.month,
                    base_date.day,
                    hour,
                    0,
                    0,
                    tzinfo=target_tz,
                )
                price = hourly_prices[hhmm_key]
                hourly_list.append(
                    {
                        "time": dt_obj,
                        "value": round(float(price), 4),
                    }
                )
            except (ValueError, AttributeError) as e:
                _LOGGER.warning(f"Failed to convert hourly interval {hhmm_key}: {e}")
                continue

        return hourly_list

    @property
    def extra_state_attributes(self):
        """Return hourly price attributes instead of interval prices."""
        # Get base attributes from parent (but we'll override the interval prices)
        attrs = super().extra_state_attributes

        if not self.coordinator.data:
            return attrs

        # Get target timezone for datetime conversion
        target_tz = dt_util.get_default_time_zone()
        now = dt_util.now().astimezone(target_tz)

        # Calculate hourly averages for today and tomorrow
        today_hourly = {}
        tomorrow_hourly = {}

        # Get interval prices from coordinator data (properties)
        today_intervals = (
            self.coordinator.data.today_interval_prices if self.coordinator.data else {}
        )
        tomorrow_intervals = (
            self.coordinator.data.tomorrow_interval_prices
            if self.coordinator.data
            else {}
        )

        # Calculate hourly averages for today
        if today_intervals:
            hourly_data = {}
            for interval_key, price in today_intervals.items():
                try:
                    hour = interval_key.split(":")[0]
                    hour_key = f"{hour}:00"
                    if hour_key not in hourly_data:
                        hourly_data[hour_key] = []
                    hourly_data[hour_key].append(float(price))
                except (ValueError, AttributeError):
                    continue

            for hour_key, prices in hourly_data.items():
                if prices:
                    today_hourly[hour_key] = sum(prices) / len(prices)

        # Calculate hourly averages for tomorrow
        if tomorrow_intervals:
            hourly_data = {}
            for interval_key, price in tomorrow_intervals.items():
                try:
                    hour = interval_key.split(":")[0]
                    hour_key = f"{hour}:00"
                    if hour_key not in hourly_data:
                        hourly_data[hour_key] = []
                    hourly_data[hour_key].append(float(price))
                except (ValueError, AttributeError):
                    continue

            for hour_key, prices in hourly_data.items():
                if prices:
                    tomorrow_hourly[hour_key] = sum(prices) / len(prices)

        # Convert to list format with datetime objects
        today_date = now.date()
        tomorrow_date = (now + timedelta(days=1)).date()

        attrs["today_hourly_prices"] = self._convert_hourly_to_list(
            today_hourly, today_date
        )
        attrs["tomorrow_hourly_prices"] = self._convert_hourly_to_list(
            tomorrow_hourly, tomorrow_date
        )

        # Add statistics for today's hourly prices
        if today_hourly:
            values = list(today_hourly.values())
            attrs["today_min_price"] = round(min(values), 5)
            attrs["today_max_price"] = round(max(values), 5)
            attrs["today_avg_price"] = round(sum(values) / len(values), 5)

        # Add statistics for tomorrow's hourly prices
        if tomorrow_hourly:
            values = list(tomorrow_hourly.values())
            attrs["tomorrow_min_price"] = round(min(values), 5)
            attrs["tomorrow_max_price"] = round(max(values), 5)
            attrs["tomorrow_avg_price"] = round(sum(values) / len(values), 5)

        # Remove the 15-minute interval prices from attributes for hourly sensors
        # These sensors focus on hourly data, not interval data
        attrs.pop("today_interval_prices", None)
        attrs.pop("tomorrow_interval_prices", None)

        return attrs


class TomorrowHourlyAverageSensor(TomorrowSensorMixin, HourlyAverageSensor):
    """Hourly average price sensor for tomorrow with proper availability."""

    pass

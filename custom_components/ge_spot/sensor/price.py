"""Price-specific sensor implementations."""
import logging
from typing import Any, Dict, Optional, Callable
from datetime import datetime

from homeassistant.util import dt as dt_util

from .base import BaseElectricityPriceSensor

_LOGGER = logging.getLogger(__name__)

class PriceValueSensor(BaseElectricityPriceSensor):
    """Generic sensor for price values with flexible data extraction."""

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, value_fn, additional_attrs=None):
        """Initialize the price value sensor."""
        super().__init__(coordinator, config_data, sensor_type, name_suffix)
        self._value_fn = value_fn
        self._additional_attrs = additional_attrs

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None
        return self._value_fn(self.coordinator.data)

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
            if "adapter" in self.coordinator.data and hasattr(self.coordinator.data["adapter"], "get_prices_with_timestamps"):
                adapter = self.coordinator.data["adapter"]

                # Get today prices with timestamps
                today_prices = adapter.get_prices_with_timestamps(0)
                # Format for display
                if today_prices:
                    attrs["today_with_timestamps"] = self._format_timestamp_display(today_prices)

                # Add tomorrow prices with timestamps if available
                if adapter.is_tomorrow_valid():
                    tomorrow_prices = adapter.get_prices_with_timestamps(1)
                    if tomorrow_prices:
                        attrs["tomorrow_with_timestamps"] = self._format_timestamp_display(tomorrow_prices)

                # Add fallback API data if available
                if "fallback_adapters" in self.coordinator.data:
                    fallback_adapters = self.coordinator.data["fallback_adapters"]
                    for source, fb_adapter in fallback_adapters.items():
                        if hasattr(fb_adapter, "get_prices_with_timestamps"):
                            # Add today prices from fallback source
                            today_fb_prices = fb_adapter.get_prices_with_timestamps(0)
                            if today_fb_prices:
                                attrs[f"today_{source}_with_timestamps"] = self._format_timestamp_display(today_fb_prices)

                            # Add tomorrow prices from fallback source if available
                            if fb_adapter.is_tomorrow_valid():
                                tomorrow_fb_prices = fb_adapter.get_prices_with_timestamps(1)
                                if tomorrow_fb_prices:
                                    attrs[f"tomorrow_{source}_with_timestamps"] = self._format_timestamp_display(tomorrow_fb_prices)

                # Remove raw price list
                attrs.pop("today", None)
                attrs.pop("tomorrow", None)

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
        self._day_offset = day_offset  # 0 for today, 1 for tomorrow
        self._extrema_type = extrema_type  # "min" or "max"
        self._stats_key = "today_stats" if day_offset == 0 else "tomorrow_stats"

        # Create value extraction function
        def extract_value(data):
            if self._stats_key not in data:
                return None
            key = "min" if self._extrema_type == "min" else "max"
            return data[self._stats_key].get(key)

        def get_timestamp(data):
            from homeassistant.util import dt as dt_util
            if self._stats_key not in data:
                return {}

            stats = data[self._stats_key]
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

    def __init__(self, coordinator, entity_id, name, stat_type, include_vat=False, vat=0, price_in_cents=False):
        """Initialize the price statistic sensor."""
        # Create value extraction function
        def extract_value(data):
            if "today_stats" not in data:
                return None
            return data["today_stats"].get(stat_type)

        # Initialize parent class
        super().__init__(
            coordinator,
            {
                "area": coordinator.area,
                "currency": coordinator.currency,
                "vat": vat,
                "precision": 3
            },
            f"{stat_type}_price",
            name,
            extract_value,
            None
        )
        self._stat_type = stat_type
        self._include_vat = include_vat
        self._price_in_cents = price_in_cents


class PriceDifferenceSensor(PriceValueSensor):
    """Sensor for price difference between two values."""

    def __init__(self, coordinator, entity_id, name, value1_key, value2_key, 
                include_vat=False, vat=0, price_in_cents=False):
        """Initialize the price difference sensor."""
        # Create value extraction function
        def extract_value(data):
            if value1_key not in data or value2_key not in data:
                return None
                
            value1 = data.get(value1_key)
            if value1_key == "current_price" and value1 is None:
                # Try to get from today_stats
                if "today_stats" in data:
                    value1 = data["today_stats"].get("current")
                    
            value2 = None
            if value2_key == "average":
                # Get from today_stats
                if "today_stats" in data:
                    value2 = data["today_stats"].get("average")
            else:
                value2 = data.get(value2_key)
                
            if value1 is None or value2 is None:
                return None
                
            return value1 - value2

        # Initialize parent class
        super().__init__(
            coordinator,
            {
                "area": coordinator.area,
                "currency": coordinator.currency,
                "vat": vat,
                "precision": 3
            },
            "price_difference",
            name,
            extract_value,
            None
        )
        self._value1_key = value1_key
        self._value2_key = value2_key
        self._include_vat = include_vat
        self._price_in_cents = price_in_cents


class PricePercentSensor(PriceValueSensor):
    """Sensor for price percentage relative to a reference value."""

    def __init__(self, coordinator, entity_id, name, value_key, reference_key, 
                include_vat=False, vat=0):
        """Initialize the price percentage sensor."""
        # Create value extraction function
        def extract_value(data):
            if value_key not in data:
                return None
                
            value = data.get(value_key)
            if value_key == "current_price" and value is None:
                # Try to get from today_stats
                if "today_stats" in data:
                    value = data["today_stats"].get("current")
                    
            reference = None
            if reference_key == "average":
                # Get from today_stats
                if "today_stats" in data:
                    reference = data["today_stats"].get("average")
            else:
                reference = data.get(reference_key)
                
            if value is None or reference is None or reference == 0:
                return None
                
            return (value / reference - 1) * 100

        # Initialize parent class
        super().__init__(
            coordinator,
            {
                "area": coordinator.area,
                "currency": coordinator.currency,
                "vat": vat,
                "precision": 1
            },
            "price_percentage",
            name,
            extract_value,
            None
        )
        self._value_key = value_key
        self._reference_key = reference_key
        self._include_vat = include_vat
        
    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"


class OffPeakPeakSensor(PriceValueSensor):
    """Sensor for off-peak and peak price periods."""

    def __init__(self, coordinator, entity_id, name, include_vat=False, vat=0, price_in_cents=False):
        """Initialize the off-peak/peak sensor."""
        # Create value extraction function that returns a string representation
        def extract_value(data):
            if "today_stats" not in data:
                return None
                
            stats = data["today_stats"]
            if "peak" not in stats or "off_peak" not in stats:
                return None
                
            peak = stats["peak"]
            off_peak = stats["off_peak"]
            
            if not peak or not off_peak:
                return None
                
            peak_avg = peak.get("average")
            off_peak_avg = off_peak.get("average")
            
            if peak_avg is None or off_peak_avg is None:
                return None
                
            # Return the ratio between peak and off-peak
            return peak_avg / off_peak_avg if off_peak_avg != 0 else None

        # Initialize parent class
        super().__init__(
            coordinator,
            {
                "area": coordinator.area,
                "currency": coordinator.currency,
                "vat": vat,
                "precision": 2
            },
            "peak_offpeak",
            name,
            extract_value,
            self._get_additional_attrs
        )
        self._include_vat = include_vat
        self._price_in_cents = price_in_cents
        
    def _get_additional_attrs(self, data):
        """Get additional attributes for the sensor."""
        if "today_stats" not in data:
            return {}
            
        stats = data["today_stats"]
        if "peak" not in stats or "off_peak" not in stats:
            return {}
            
        peak = stats["peak"]
        off_peak = stats["off_peak"]
        
        if not peak or not off_peak:
            return {}
            
        return {
            "peak_average": peak.get("average"),
            "peak_min": peak.get("min"),
            "peak_max": peak.get("max"),
            "peak_hours": peak.get("hours", []),
            "off_peak_average": off_peak.get("average"),
            "off_peak_min": off_peak.get("min"),
            "off_peak_max": off_peak.get("max"),
            "off_peak_hours": off_peak.get("hours", [])
        }
        
    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "ratio"

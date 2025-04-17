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

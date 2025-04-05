"""Support for electricity price sensors."""
import logging
import datetime
from typing import Any, Dict, Optional, List

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


class PriceExtremaSensorBase(BaseElectricityPriceSensor):
    """Base class for min/max price sensors."""

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, day_offset=0, extrema_type="min"):
        """Initialize the extrema price sensor."""
        super().__init__(coordinator, config_data, sensor_type, name_suffix)
        self._day_offset = day_offset  # 0 for today, 1 for tomorrow
        self._extrema_type = extrema_type  # "min" or "max"
        self._stats_key = "today_stats" if day_offset == 0 else "tomorrow_stats"

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False

        # For tomorrow sensors, check if tomorrow data is valid
        if self._day_offset > 0 and not self.coordinator.data.get(ATTR_TOMORROW_VALID, False):
            return False

        return True

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or self._stats_key not in self.coordinator.data:
            return None

        # Get min or max based on extrema_type
        attr_key = "min" if self._extrema_type == "min" else "max"
        const_attr = ATTR_MIN if self._extrema_type == "min" else ATTR_MAX

        return self.coordinator.data[self._stats_key].get(attr_key) or self.coordinator.data[self._stats_key].get(const_attr)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        if not self.coordinator.data or self._stats_key not in self.coordinator.data:
            return attrs

        # Add timestamp for extrema price
        timestamp_key = f"{self._extrema_type}_timestamp"
        if timestamp_key in self.coordinator.data[self._stats_key]:
            attrs["timestamp"] = self.coordinator.data[self._stats_key][timestamp_key]

        return attrs


class CurrentPriceSensor(BaseElectricityPriceSensor):
    """Sensor for current electricity price."""

    def __init__(self, coordinator, config_data):
        """Initialize the current price sensor."""
        super().__init__(coordinator, config_data, "current_price", "Current Price")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("current_price")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes
        if not self.coordinator.data:
            return attrs

        # Include essential price data
        attrs.update({
            ATTR_TODAY: self.coordinator.data.get(ATTR_TODAY, []),
            ATTR_TOMORROW: self.coordinator.data.get(ATTR_TOMORROW, []),
            ATTR_TOMORROW_VALID: self.coordinator.data.get(ATTR_TOMORROW_VALID, False),
        })

        # Add API key status if available
        if ATTR_API_KEY_STATUS in self.coordinator.data:
            api_key_status = self.coordinator.data.get(ATTR_API_KEY_STATUS, {})

            # Add ENTSO-E API key status if relevant
            if SOURCE_ENTSO_E in api_key_status:
                status = api_key_status[SOURCE_ENTSO_E]
                attrs["entso_e_api_key"] = {
                    "configured": status.get("configured", False),
                    "status": status.get("status", "unknown"),
                    "valid": status.get("valid", None)
                }

        # Add exchange rate info
        if "exchange_rate_info" in self.coordinator.data:
            exchange_info = self.coordinator.data["exchange_rate_info"]
            if exchange_info and "timestamp" in exchange_info:
                attrs["exchange_service_timestamp"] = exchange_info.get("timestamp")
                if "formatted" in exchange_info:
                    attrs["exchange_service_rate"] = exchange_info.get("formatted")
                elif "rate" in exchange_info:
                    attrs["exchange_service_rate"] = f"1 EUR = {exchange_info['rate']:.4f} {self._currency}"

        return attrs


class NextHourPriceSensor(BaseElectricityPriceSensor):
    """Sensor for next hour electricity price."""

    def __init__(self, coordinator, config_data):
        """Initialize the next hour price sensor."""
        super().__init__(coordinator, config_data, "next_hour_price", "Next Hour Price")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data is None or "adapter" not in self.coordinator.data:
            return None

        # Use Home Assistant's dt_util to get the current time
        now = dt_util.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)

        adapter = self.coordinator.data["adapter"]
        return adapter.get_current_price(reference_time=next_hour)


class DayAveragePriceSensor(BaseElectricityPriceSensor):
    """Sensor for day average electricity price."""

    def __init__(self, coordinator, config_data):
        """Initialize the day average price sensor."""
        super().__init__(coordinator, config_data, "day_average_price", "Day Average")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "today_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["today_stats"].get("average")


class PeakPriceSensor(PriceExtremaSensorBase):
    """Sensor for peak electricity price."""
    def __init__(self, coordinator, config_data):
        """Initialize the peak price sensor."""
        super().__init__(
            coordinator,
            config_data,
            "peak_price",
            "Peak Price",
            day_offset=0,
            extrema_type="max"
        )


class OffPeakPriceSensor(PriceExtremaSensorBase):
    """Sensor for off-peak electricity price."""
    def __init__(self, coordinator, config_data):
        """Initialize the off-peak price sensor."""
        super().__init__(
            coordinator,
            config_data,
            "off_peak_price",
            "Off-Peak Price",
            day_offset=0,
            extrema_type="min"
        )


class TomorrowAveragePriceSensor(BaseElectricityPriceSensor):
    """Sensor for tomorrow's average electricity price."""

    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow average price sensor."""
        super().__init__(coordinator, config_data, "tomorrow_average_price", "Tomorrow Average")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data or "tomorrow_stats" not in self.coordinator.data:
            return None
        return self.coordinator.data["tomorrow_stats"].get("average")

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
        # Only available if tomorrow data is valid
        return self.coordinator.data.get(ATTR_TOMORROW_VALID, False)


class TomorrowPeakPriceSensor(PriceExtremaSensorBase):
    """Sensor for tomorrow's peak electricity price."""
    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow peak price sensor."""
        super().__init__(
            coordinator,
            config_data,
            "tomorrow_peak_price",
            "Tomorrow Peak",
            day_offset=1,
            extrema_type="max"
        )


class TomorrowOffPeakPriceSensor(PriceExtremaSensorBase):
    """Sensor for tomorrow's off-peak electricity price."""
    def __init__(self, coordinator, config_data):
        """Initialize the tomorrow off-peak price sensor."""
        super().__init__(
            coordinator,
            config_data,
            "tomorrow_off_peak_price",
            "Tomorrow Off-Peak",
            day_offset=1,
            extrema_type="min"
        )


async def async_setup_entry(hass, config_entry, async_add_entities):
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

    entities = [
        CurrentPriceSensor(coordinator, config_data),
        NextHourPriceSensor(coordinator, config_data),
        DayAveragePriceSensor(coordinator, config_data),
        PeakPriceSensor(coordinator, config_data),
        OffPeakPriceSensor(coordinator, config_data),
        TomorrowAveragePriceSensor(coordinator, config_data),
        TomorrowPeakPriceSensor(coordinator, config_data),
        TomorrowOffPeakPriceSensor(coordinator, config_data),
    ]

    async_add_entities(entities)

"""Base sensor for electricity prices."""
import logging
from typing import Dict, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..const.attributes import Attributes
from ..const.config import Config
from ..const.currencies import Currency, CurrencyInfo
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.network import Network

_LOGGER = logging.getLogger(__name__)

class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""

    _attr_state_class = None  # Prices are instantaneous, not totals. History still recorded.
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        if not isinstance(config_data, dict):
            raise TypeError("config_data must be a dictionary")
        self._area = config_data.get(Attributes.AREA)
        self._vat = config_data.get(Attributes.VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type

        # Display settings
        self._display_unit = config_data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT) # Get from config_data
        # Determine if subunit should be used based on the display_unit setting
        self._use_subunit = self._display_unit == DisplayUnit.CENTS # Correctly determine based on _display_unit
        self._currency = config_data.get(Attributes.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(self._area))

        # Create entity ID and name
        if self._area:
            area_lower = self._area.lower()
            self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{area_lower}"
            self._attr_name = f"GE-Spot {name_suffix} {self._area}"
            self._attr_unique_id = f"gespot_{sensor_type}_{area_lower}"
        else:
            # Log an error and potentially set default/invalid values or raise to prevent setup
            _LOGGER.error("Area is not configured or is None. Cannot create sensor entity.")
            # Option 1: Set dummy values (might hide the config issue)
            # self.entity_id = f"sensor.gespot_{sensor_type.lower()}_invalid_area"
            # self._attr_name = f"GE-Spot {name_suffix} (Invalid Area)"
            # self._attr_unique_id = f"gespot_{sensor_type}_invalid_area"
            # Option 2: Raise an error to clearly signal failed setup (might be better)
            raise ValueError("Area configuration is missing, cannot initialize sensor.")


        # Set unit based on display_unit configuration
        if self._use_subunit:
            subunit = CurrencyInfo.SUBUNIT_NAMES.get(self._currency, "cents")
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

        # Initialize attributes dictionary
        attrs = {
            "currency": self._currency,
            "area": self._area,
            "vat": f"{self._vat * 100:.0f}%",
            "display_unit": self._display_unit,
            "use_subunit": self._use_subunit,
            # Corrected: Use 'data_source' from coordinator data
            "data_source": self.coordinator.data.get("data_source", "unknown"),
        }

        # Add timestamps if available
        # Corrected: Use 'last_fetch_attempt' key
        if "last_fetch_attempt" in self.coordinator.data:
            attrs["last_api_fetch"] = self.coordinator.data["last_fetch_attempt"]

        # Add simplified source info
        source_info = {}

        # Show validated sources (what's been tested and working)
        validated_sources = self.coordinator.data.get("validated_sources")
        if validated_sources:
            source_info["validated_sources"] = validated_sources

        # Show failed sources with details
        failed_sources = self.coordinator.data.get("failed_sources")
        if failed_sources:
            source_info["failed_sources"] = failed_sources

        # Show active source (what's currently used)
        active_source = self.coordinator.data.get("data_source")
        if active_source and active_source not in ("unknown", "None"):
            source_info["active_source"] = active_source

        # Add API key status if available
        if "api_key_status" in self.coordinator.data:
            source_info["api_key_status"] = self.coordinator.data["api_key_status"]

        # Add rate limit info (dynamic only)
        if "next_fetch_allowed_in_seconds" in self.coordinator.data:
            source_info["next_fetch_allowed_in_seconds"] = self.coordinator.data["next_fetch_allowed_in_seconds"]

        # Only add source_info if it contains data
        if source_info:
            attrs["source_info"] = source_info

        # Add timezone info
        # Corrected: Use 'target_timezone' key for HA timezone
        if "target_timezone" in self.coordinator.data:
            attrs["ha_timezone"] = self.coordinator.data["target_timezone"]

        # Corrected: Use 'source_timezone' key for API timezone
        if "source_timezone" in self.coordinator.data:
            attrs["api_timezone"] = self.coordinator.data["source_timezone"]

        # Add data validity information
        if "data_validity" in self.coordinator.data:
            validity_dict = self.coordinator.data["data_validity"]
            if isinstance(validity_dict, dict):
                # Add data validity info for monitoring
                data_validity_info = {}

                if validity_dict.get("data_valid_until"):
                    data_validity_info["data_valid_until"] = validity_dict["data_valid_until"]

                if validity_dict.get("last_valid_interval"):
                    data_validity_info["last_valid_interval"] = validity_dict["last_valid_interval"]

                data_validity_info["interval_count"] = validity_dict.get("interval_count", 0)
                data_validity_info["today_intervals"] = validity_dict.get("today_interval_count", 0)
                data_validity_info["tomorrow_intervals"] = validity_dict.get("tomorrow_interval_count", 0)
                data_validity_info["has_current_interval"] = validity_dict.get("has_current_interval", False)

                # Calculate intervals remaining (if we have validity data)
                if validity_dict.get("data_valid_until"):
                    from homeassistant.util import dt as dt_util
                    from ..coordinator.data_validity import DataValidity

                    try:
                        # Reconstruct DataValidity to calculate intervals_remaining
                        validity = DataValidity.from_dict(validity_dict)
                        now = dt_util.now()
                        intervals_remaining = validity.intervals_remaining(now)
                        data_validity_info["intervals_remaining"] = intervals_remaining
                    except Exception as e:
                        _LOGGER.warning(f"Failed to calculate intervals_remaining: {e}")

                attrs["data_validity"] = data_validity_info

        # Add error information if present (for diagnostics)
        if "error" in self.coordinator.data and self.coordinator.data["error"]:
            error_info = {"message": self.coordinator.data["error"]}
            if "error_code" in self.coordinator.data and self.coordinator.data["error_code"]:
                error_info["code"] = self.coordinator.data["error_code"]
            attrs["error"] = error_info

        # Add interval prices if available, rounding float values
        if "interval_prices" in self.coordinator.data:
            interval_prices = self.coordinator.data["interval_prices"]
            if isinstance(interval_prices, dict):
                attrs["interval_prices"] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in interval_prices.items()
                }
            else:
                attrs["interval_prices"] = interval_prices # Keep original if not a dict

        # Add tomorrow interval prices if available, rounding float values
        if "tomorrow_interval_prices" in self.coordinator.data:
            tomorrow_interval_prices = self.coordinator.data["tomorrow_interval_prices"]
            if isinstance(tomorrow_interval_prices, dict):
                attrs["tomorrow_interval_prices"] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in tomorrow_interval_prices.items()
                }
            else:
                attrs["tomorrow_interval_prices"] = tomorrow_interval_prices # Keep original if not a dict

        # Add error message if available
        if "error" in self.coordinator.data and self.coordinator.data["error"]:
            attrs["error"] = self.coordinator.data["error"]

        return attrs

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()

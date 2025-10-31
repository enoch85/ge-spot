"""Base sensor for electricity prices."""

import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from ..const.attributes import Attributes
from ..const.config import Config
from ..const.currencies import CurrencyInfo
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..coordinator.data_processor import parse_interval_key
from ..coordinator.data_validity import DataValidity

_LOGGER = logging.getLogger(__name__)


class BaseElectricityPriceSensor(SensorEntity):
    """Base sensor for electricity prices."""

    _attr_state_class = (
        None  # Prices are instantaneous, not totals. History still recorded.
    )
    _attr_device_class = SensorDeviceClass.MONETARY

    # Exclude large interval price arrays from database to prevent bloat
    # These are operational data for automations, not historical data
    # The main sensor value (current_price) provides historical tracking
    _unrecorded_attributes = frozenset(
        {
            "today_interval_prices",
            "tomorrow_interval_prices",
        }
    )

    def __init__(self, coordinator, config_data, sensor_type, name_suffix):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        if not isinstance(config_data, dict):
            raise TypeError("config_data must be a dictionary")

        # Store timezone service for EV Smart Charging attribute conversion
        self._tz_service = getattr(coordinator, "_tz_service", None)

        self._area = config_data.get(Attributes.AREA)
        self._vat = config_data.get(Attributes.VAT, 0)
        self._precision = config_data.get("precision", 3)
        self._sensor_type = sensor_type

        # Display settings
        self._display_unit = config_data.get(
            Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT
        )  # Get from config_data
        # Determine if subunit should be used based on the display_unit setting
        self._use_subunit = (
            self._display_unit == DisplayUnit.CENTS
        )  # Correctly determine based on _display_unit
        self._currency = config_data.get(
            Attributes.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(self._area)
        )

        # Create entity ID and name
        if self._area:
            area_lower = self._area.lower()
            self.entity_id = f"sensor.gespot_{sensor_type.lower()}_{area_lower}"
            self._attr_name = f"GE-Spot {name_suffix} {self._area}"
            self._attr_unique_id = f"gespot_{sensor_type}_{area_lower}"
        else:
            # Log an error and potentially set default/invalid values or raise to prevent setup
            _LOGGER.error(
                "Area is not configured or is None. Cannot create sensor entity."
            )
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
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        # Initialize attributes dictionary
        attrs = {
            "currency": self._currency,
            "area": self._area,
            "vat": f"{self._vat * 100:.1f}%",
            "display_unit": self._display_unit,
            "use_subunit": self._use_subunit,
            # Access source directly from IntervalPriceData
            "data_source": (
                self.coordinator.data.source if self.coordinator.data else "unknown"
            ),
        }

        # Add timestamps if available
        if self.coordinator.data and hasattr(
            self.coordinator.data, "_last_fetch_attempt"
        ):
            attrs["last_api_fetch"] = self.coordinator.data._last_fetch_attempt

        # Add simplified source info
        source_info = {}

        # Show validated sources (what's been tested and working)
        if self.coordinator.data and hasattr(self.coordinator, 'price_manager'):
            # Get live validated sources from coordinator's price manager (not cached snapshot)
            validated_sources = self.coordinator.price_manager.get_validated_sources()
            if validated_sources:
                source_info["validated_sources"] = validated_sources

        # Show failed sources with details
        if self.coordinator.data and hasattr(self.coordinator, 'price_manager'):
            # Get live failed source details from coordinator's price manager
            failed_source_details = self.coordinator.price_manager.get_failed_source_details()
            if failed_source_details:
                source_info["failed_sources"] = failed_source_details

        # Show active source (what's currently used) - but not if it's redundant with Data source
        # Only show active_source in source_info if we have other info to display
        # (Otherwise users see it twice: once as "Data source" and once as "active_source")

        # Only add source_info if it contains data
        if source_info:
            # Add active source to source_info only if we have other diagnostic info
            if self.coordinator.data and self.coordinator.data.source not in (
                "unknown",
                "None",
            ):
                source_info["active_source"] = self.coordinator.data.source
            attrs["source_info"] = source_info

        # Add timezone info
        if self.coordinator.data and self.coordinator.data.target_timezone:
            attrs["ha_timezone"] = self.coordinator.data.target_timezone

        if self.coordinator.data and self.coordinator.data.source_timezone:
            attrs["api_timezone"] = self.coordinator.data.source_timezone

        # Add data validity information (computed property)
        if self.coordinator.data:
            validity = self.coordinator.data.data_validity
            if validity:
                # Add data validity info for monitoring
                data_validity_info = {}

                if validity.data_valid_until:
                    data_validity_info["data_valid_until"] = (
                        validity.data_valid_until.isoformat()
                        if hasattr(validity.data_valid_until, "isoformat")
                        else str(validity.data_valid_until)
                    )

                if validity.last_valid_interval:
                    data_validity_info["last_valid_interval"] = (
                        validity.last_valid_interval
                    )

                data_validity_info["interval_count"] = validity.interval_count
                data_validity_info["today_intervals"] = validity.today_interval_count
                data_validity_info["tomorrow_intervals"] = (
                    validity.tomorrow_interval_count
                )
                data_validity_info["has_current_interval"] = (
                    validity.has_current_interval
                )

                # Calculate intervals remaining
                try:
                    now = dt_util.now()
                    intervals_remaining = validity.intervals_remaining(now)
                    data_validity_info["intervals_remaining"] = intervals_remaining
                except Exception as e:
                    _LOGGER.warning(f"Failed to calculate intervals_remaining: {e}")

                attrs["data_validity"] = data_validity_info

        # Add error information if present (for diagnostics)
        if self.coordinator.data and hasattr(self.coordinator.data, "_error"):
            error_msg = self.coordinator.data._error
            if error_msg:
                error_info = {"message": error_msg}
                if (
                    hasattr(self.coordinator.data, "_error_code")
                    and self.coordinator.data._error_code
                ):
                    error_info["code"] = self.coordinator.data._error_code
                attrs["error"] = error_info

        # Add interval prices in list format with datetime objects (v1.5.0)
        # Format: [{"time": datetime object, "value": float}, ...]
        # External integrations (EV Smart Charging) expect this format

        # Get target timezone
        target_tz = None
        if self._tz_service:
            target_tz = self._tz_service.target_timezone
        else:
            # Fallback to HA default timezone
            target_tz = dt_util.get_default_time_zone()

        # Convert today's prices from HH:MM dict to list of datetime objects
        if self.coordinator.data and self.coordinator.data.today_interval_prices:
            today_prices = self.coordinator.data.today_interval_prices
            today_raw_prices = self.coordinator.data.today_raw_prices

            if isinstance(today_prices, dict) and today_prices:
                now = dt_util.now().astimezone(target_tz)
                today_date = now.date()

                today_list = []
                for hhmm_key in sorted(today_prices.keys()):
                    try:
                        hour, minute = parse_interval_key(hhmm_key)
                        dt = datetime(
                            today_date.year,
                            today_date.month,
                            today_date.day,
                            hour,
                            minute,
                            0,
                            tzinfo=target_tz,
                        )
                        price = today_prices[hhmm_key]
                        raw_price = today_raw_prices.get(hhmm_key)

                        entry = {
                            "time": dt,  # datetime object (not ISO string!)
                            "value": round(float(price), 4),
                        }

                        # Add raw_value if available (Issue #40)
                        if raw_price is not None:
                            entry["raw_value"] = round(float(raw_price), 4)

                        today_list.append(entry)
                    except (ValueError, AttributeError) as e:
                        _LOGGER.warning(f"Failed to convert interval {hhmm_key}: {e}")
                        continue

                attrs["today_interval_prices"] = today_list
            else:
                attrs["today_interval_prices"] = []
        else:
            attrs["today_interval_prices"] = []

        # Convert tomorrow's prices from HH:MM dict to list of datetime objects
        if self.coordinator.data and self.coordinator.data.tomorrow_interval_prices:
            tomorrow_prices = self.coordinator.data.tomorrow_interval_prices
            tomorrow_raw_prices = self.coordinator.data.tomorrow_raw_prices

            if isinstance(tomorrow_prices, dict) and tomorrow_prices:
                now = dt_util.now().astimezone(target_tz)
                tomorrow_date = (now + timedelta(days=1)).date()

                tomorrow_list = []
                for hhmm_key in sorted(tomorrow_prices.keys()):
                    try:
                        hour, minute = parse_interval_key(hhmm_key)
                        dt = datetime(
                            tomorrow_date.year,
                            tomorrow_date.month,
                            tomorrow_date.day,
                            hour,
                            minute,
                            0,
                            tzinfo=target_tz,
                        )
                        price = tomorrow_prices[hhmm_key]
                        raw_price = tomorrow_raw_prices.get(hhmm_key)

                        entry = {
                            "time": dt,  # datetime object (not ISO string!)
                            "value": round(float(price), 4),
                        }

                        # Add raw_value if available (Issue #40)
                        if raw_price is not None:
                            entry["raw_value"] = round(float(raw_price), 4)

                        tomorrow_list.append(entry)
                    except (ValueError, AttributeError) as e:
                        _LOGGER.warning(f"Failed to convert interval {hhmm_key}: {e}")
                        continue

                attrs["tomorrow_interval_prices"] = tomorrow_list
            else:
                attrs["tomorrow_interval_prices"] = []
        else:
            attrs["tomorrow_interval_prices"] = []

        return attrs

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        await self.coordinator.async_request_refresh()

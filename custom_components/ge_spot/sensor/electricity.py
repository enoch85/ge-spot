"""Electricity price data sensors for the GE-Spot integration."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import DOMAIN
from ..const.config import Config
from ..coordinator import UnifiedPriceCoordinator
from .price import (
    PriceValueSensor,
    PriceStatisticSensor,
    ExtremaPriceSensor,
    PriceDifferenceSensor,
    PricePercentSensor,
    TomorrowAveragePriceSensor,
    TomorrowExtremaPriceSensor,
    HourlyAverageSensor,
    TomorrowHourlyAverageSensor,
)

from ..const.attributes import Attributes
from ..const.defaults import Defaults
from ..const.display import DisplayUnit

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the GE Spot electricity sensors."""
    coordinator: UnifiedPriceCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    options = config_entry.options
    data = config_entry.data  # Get data as well

    # Prioritize options, fallback to data, then default for display_unit
    display_unit_setting = options.get(
        Config.DISPLAY_UNIT, data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
    )

    # Create a proper config_data dictionary including area and other relevant options
    config_data = {
        Attributes.AREA: coordinator.area,  # Get area from coordinator
        # Prioritize options, fallback to data, then default for VAT
        Attributes.VAT: options.get(Config.VAT, data.get(Config.VAT, 0)),
        # Prioritize options, fallback to data, then default for PRECISION
        Config.PRECISION: options.get(
            Config.PRECISION, data.get(Config.PRECISION, Defaults.PRECISION)
        ),
        # Use the resolved display_unit_setting
        Config.DISPLAY_UNIT: display_unit_setting,
        # Prioritize options, fallback to data, then default for CURRENCY
        Attributes.CURRENCY: options.get(
            Config.CURRENCY, data.get(Config.CURRENCY, coordinator.currency)
        ),
        "entry_id": config_entry.entry_id,
    }

    # Define value extraction functions (data is IntervalPriceData object, not dict)
    get_current_price = lambda data: data.current_price
    get_next_interval_price = lambda data: data.next_interval_price
    # Define a simple additional attributes function
    get_base_attrs = lambda data: {
        "tomorrow_valid": data.tomorrow_valid if data else False
    }

    entities = []

    # Get specific settings used by some sensors directly (already present)
    vat = options.get(Config.VAT, 0) / 100  # Convert from percentage to decimal
    include_vat = options.get(Config.INCLUDE_VAT, False)
    price_in_cents = (
        display_unit_setting == DisplayUnit.CENTS
    )  # Use resolved display_unit_setting

    # Create sensor entities (passing the populated config_data)

    # Current price sensor
    entities.append(
        PriceValueSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "current_price",  # Pass only the sensor type
            "Current Price",
            get_current_price,  # Pass the function
            get_base_attrs,  # Pass the function for additional attributes
        )
    )

    # Next interval price sensor
    entities.append(
        PriceValueSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "next_interval_price",  # Pass only the sensor type
            "Next Interval Price",
            get_next_interval_price,  # Pass the function
            None,  # No specific additional attributes needed here yet
        )
    )

    # Average price sensor
    entities.append(
        PriceStatisticSensor(
            coordinator,
            config_data,  # Pass config_data
            "average_price",  # Pass only the sensor type
            "Average Price",
            "avg",
        )
    )

    # Peak price sensor
    entities.append(
        ExtremaPriceSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "peak_price",  # Pass only the sensor type
            "Peak Price",
            extrema_type="max",  # Removed additional_attrs
        )
    )

    # Off-peak price sensor
    entities.append(
        ExtremaPriceSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "off_peak_price",  # Pass only the sensor type
            "Off-Peak Price",
            extrema_type="min",  # Removed additional_attrs
        )
    )

    # Price difference (current vs average)
    entities.append(
        PriceDifferenceSensor(
            coordinator,
            config_data,  # Pass config_data
            "price_difference",  # Pass only the sensor type
            "Price Difference",
            "current_price",
            "average",
        )
    )

    # Price percentage (current vs average)
    entities.append(
        PricePercentSensor(
            coordinator,
            config_data,  # Pass config_data
            "price_percentage",  # Pass only the sensor type
            "Price Percentage",
            "current_price",
            "average",
        )
    )

    # --- Add Tomorrow Sensors ---

    # Tomorrow Average price sensor
    # Define value extraction function for tomorrow average
    get_tomorrow_avg_price = lambda data: (
        data.tomorrow_statistics.avg if data and data.tomorrow_statistics else None
    )
    entities.append(
        TomorrowAveragePriceSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "tomorrow_average_price",  # Pass only the sensor type
            "Tomorrow Average Price",
            get_tomorrow_avg_price,  # Pass the function
            additional_attrs=get_base_attrs,  # Keep here, TomorrowAveragePriceSensor inherits from PriceValueSensor correctly
        )
    )

    # Tomorrow Peak price sensor
    entities.append(
        TomorrowExtremaPriceSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "tomorrow_peak_price",  # Pass only the sensor type
            "Tomorrow Peak Price",
            day_offset=1,  # Specify tomorrow
            extrema_type="max",  # Specify peak
        )
    )

    # Tomorrow Off-Peak price sensor
    entities.append(
        TomorrowExtremaPriceSensor(
            coordinator,
            config_data,  # Pass the correctly populated config_data
            "tomorrow_off_peak_price",  # Pass only the sensor type
            "Tomorrow Off-Peak Price",
            day_offset=1,  # Specify tomorrow
            extrema_type="min",  # Specify off-peak
        )
    )
    # --- End Tomorrow Sensors ---

    # --- Add Hourly Average Sensors ---

    # Hourly Average Price sensor (today)
    entities.append(
        HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )
    )

    # Tomorrow Hourly Average Price sensor
    entities.append(
        TomorrowHourlyAverageSensor(
            coordinator,
            config_data,
            "tomorrow_hourly_average_price",
            "Tomorrow Hourly Average Price",
            day_offset=1,
        )
    )
    # --- End Hourly Average Sensors ---

    # --- Export/Production Price Sensors ---
    # Only add export sensors if export is enabled in config
    export_enabled = options.get(
        Config.EXPORT_ENABLED, data.get(Config.EXPORT_ENABLED, False)
    )

    if export_enabled:
        # Define attribute function that includes export interval prices for automations
        # This mirrors how import sensors expose today_interval_prices/tomorrow_interval_prices
        def get_export_attrs(data):
            """Get export price attributes including interval prices for automations."""
            attrs = {"tomorrow_valid": data.tomorrow_valid if data else False}

            # Add export interval prices for automation access
            if data and data.export_today_prices:
                # Convert to list format consistent with import prices
                today_list = []
                for key in sorted(data.export_today_prices.keys()):
                    today_list.append(
                        {
                            "time": key,
                            "value": round(float(data.export_today_prices[key]), 4),
                        }
                    )
                attrs["export_today_prices"] = today_list
            else:
                attrs["export_today_prices"] = []

            if data and data.export_tomorrow_prices:
                tomorrow_list = []
                for key in sorted(data.export_tomorrow_prices.keys()):
                    tomorrow_list.append(
                        {
                            "time": key,
                            "value": round(float(data.export_tomorrow_prices[key]), 4),
                        }
                    )
                attrs["export_tomorrow_prices"] = tomorrow_list
            else:
                attrs["export_tomorrow_prices"] = []

            return attrs

        # Export Current Price sensor
        get_export_current_price = lambda data: (
            data.export_current_price if data else None
        )
        entities.append(
            PriceValueSensor(
                coordinator,
                config_data,
                "export_current_price",
                "Export Current Price",
                get_export_current_price,
                get_export_attrs,  # Use export attrs with interval prices
            )
        )

        # Export Next Interval Price sensor
        get_export_next_price = lambda data: (
            data.export_next_interval_price if data else None
        )
        entities.append(
            PriceValueSensor(
                coordinator,
                config_data,
                "export_next_interval_price",
                "Export Next Interval Price",
                get_export_next_price,
                None,
            )
        )

        # Export Average Price sensor (today)
        get_export_avg = lambda data: (
            data.export_statistics.avg if data and data.export_statistics else None
        )
        entities.append(
            PriceValueSensor(
                coordinator,
                config_data,
                "export_average_price",
                "Export Average Price",
                get_export_avg,
                None,
            )
        )

        # Export Peak Price sensor
        get_export_peak = lambda data: (
            data.export_statistics.max if data and data.export_statistics else None
        )
        entities.append(
            PriceValueSensor(
                coordinator,
                config_data,
                "export_peak_price",
                "Export Peak Price",
                get_export_peak,
                None,
            )
        )

        # Export Off-Peak Price sensor
        get_export_off_peak = lambda data: (
            data.export_statistics.min if data and data.export_statistics else None
        )
        entities.append(
            PriceValueSensor(
                coordinator,
                config_data,
                "export_off_peak_price",
                "Export Off-Peak Price",
                get_export_off_peak,
                None,
            )
        )

        # Tomorrow Export Average Price sensor
        get_tomorrow_export_avg = lambda data: (
            data.export_tomorrow_statistics.avg
            if data and data.export_tomorrow_statistics
            else None
        )
        entities.append(
            TomorrowAveragePriceSensor(
                coordinator,
                config_data,
                "tomorrow_export_average_price",
                "Tomorrow Export Average Price",
                get_tomorrow_export_avg,
                additional_attrs=get_base_attrs,
            )
        )

        _LOGGER.debug(f"Added export price sensors for area {coordinator.area}")
    # --- End Export Price Sensors ---

    # Add all entities
    async_add_entities(entities)

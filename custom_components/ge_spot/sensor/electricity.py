"""Electricity price sensors setup and registration."""
import logging
import datetime
from typing import Any, Dict, List

from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    ATTR_AREA,
    ATTR_VAT,
    ATTR_CURRENCY,
    ATTR_TODAY,
    ATTR_TOMORROW,
    ATTR_TOMORROW_VALID,
    ATTR_API_KEY_STATUS,
    CONF_DISPLAY_UNIT,
    DEFAULT_DISPLAY_UNIT,
    REGION_TO_CURRENCY,
    SOURCE_ENTSO_E,
)
from .base import BaseElectricityPriceSensor
from .price import (
    PriceValueSensor,
    ExtremaPriceSensor,
    TomorrowExtremaPriceSensor,
    TomorrowAveragePriceSensor,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the electricity price sensors from config entries."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    area = config_entry.data.get(ATTR_AREA)
    vat = config_entry.data.get(ATTR_VAT, 0)

    # Determine currency based on area
    currency = config_entry.data.get(ATTR_CURRENCY, REGION_TO_CURRENCY.get(area))

    # Get display unit setting - first try coordinator, then config
    display_unit = None
    if hasattr(coordinator, 'display_unit'):
        display_unit = coordinator.display_unit
    else:
        display_unit = config_entry.options.get(
            CONF_DISPLAY_UNIT,
            config_entry.data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)
        )

    config_data = {
        ATTR_AREA: area,
        ATTR_VAT: vat,
        ATTR_CURRENCY: currency,
        CONF_DISPLAY_UNIT: display_unit,
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

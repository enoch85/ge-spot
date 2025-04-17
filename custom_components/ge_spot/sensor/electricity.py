"""Electricity price sensors setup and registration."""
import logging
from typing import Any, Dict, List

from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.attributes import Attributes
from ..const.defaults import Defaults
from ..const.currencies import CurrencyInfo
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
    area = config_entry.data.get(Config.AREA)

    # Get VAT from options first, then fallback to data
    vat = config_entry.options.get(Config.VAT, config_entry.data.get(Config.VAT, 0))

    # Determine currency based on area
    currency = config_entry.data.get(Config.CURRENCY, CurrencyInfo.REGION_TO_CURRENCY.get(area))

    # Get display unit setting from coordinator
    display_unit = coordinator.display_unit

    config_data = {
        Attributes.AREA: area,
        Attributes.VAT: vat,
        Attributes.CURRENCY: currency,
        Config.DISPLAY_UNIT: display_unit,
    }

    # Define sensor entities
    entities = [
        # Current price sensor
        PriceValueSensor(
            coordinator,
            config_data,
            "current_price",
            "Current Price",
            lambda data: data.get("current_price"),
            lambda data: {
                "tomorrow_valid": data.get("tomorrow_valid", False),
            }
        ),

        # Next hour price
        PriceValueSensor(
            coordinator,
            config_data,
            "next_hour_price",
            "Next Hour Price",
            lambda data: data.get("next_hour_price")
        ),

        # Day average
        PriceValueSensor(
            coordinator,
            config_data,
            "day_average_price",
            "Day Average",
            lambda data: data.get("today_stats", {}).get("average")
        ),

        # Today peak price (max)
        ExtremaPriceSensor(
            coordinator,
            config_data,
            "peak_price",
            "Peak Price",
            day_offset=0,
            extrema_type="max"
        ),

        # Today off-peak price (min)
        ExtremaPriceSensor(
            coordinator,
            config_data,
            "off_peak_price",
            "Off-Peak Price",
            day_offset=0,
            extrema_type="min"
        ),

        # Tomorrow average price
        TomorrowAveragePriceSensor(
            coordinator,
            config_data,
            "tomorrow_average_price",
            "Tomorrow Average",
            lambda data: data.get("tomorrow_stats", {}).get("average")
        ),

        # Tomorrow peak price (max)
        TomorrowExtremaPriceSensor(
            coordinator,
            config_data,
            "tomorrow_peak_price",
            "Tomorrow Peak",
            day_offset=1,
            extrema_type="max"
        ),

        # Tomorrow off-peak price (min)
        TomorrowExtremaPriceSensor(
            coordinator,
            config_data,
            "tomorrow_off_peak_price",
            "Tomorrow Off-Peak",
            day_offset=1,
            extrema_type="min"
        )
    ]

    async_add_entities(entities)

"""Electricity price data sensors for the GE-Spot integration."""
import logging
from datetime import datetime, timedelta
import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import ATTR_ATTRIBUTION

from ..const import DOMAIN
from ..const.config import Config
from ..utils.formatter import format_price, format_price_value, format_relative_price
from ..coordinator import UnifiedPriceCoordinator
from .price import (
    PriceValueSensor,
    PriceStatisticSensor,
    ExtremaPriceSensor,
    PriceDifferenceSensor,
    PricePercentSensor,
    OffPeakPeakSensor
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

    # Create a proper config_data dictionary including area and other relevant options
    config_data = {
        Attributes.AREA: coordinator.area, # Get area from coordinator
        Attributes.VAT: options.get(Config.VAT, 0), # Get VAT from options
        Config.PRECISION: options.get(Config.PRECISION, Defaults.PRECISION), # Get precision from options
        Config.DISPLAY_UNIT: options.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT), # Get display unit from options
        Attributes.CURRENCY: options.get(Config.CURRENCY, coordinator.currency), # Get currency from options
        # Add entry_id if needed elsewhere, though base sensor doesn't use it directly
        "entry_id": config_entry.entry_id,
    }

    # Define value extraction functions
    get_current_price = lambda data: data.get('current_price')
    get_next_hour_price = lambda data: data.get('next_hour_price')
    # Define a simple additional attributes function
    get_base_attrs = lambda data: {"tomorrow_valid": data.get("tomorrow_valid", False)}

    entities = []

    # Get specific settings used by some sensors directly (already present)
    vat = options.get(Config.VAT, 0) / 100  # Convert from percentage to decimal
    include_vat = options.get(Config.INCLUDE_VAT, False)
    price_in_cents = options.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS # Use DisplayUnit constant

    # Create sensor entities (passing the populated config_data)

    # Current price sensor
    entities.append(
        PriceValueSensor(
            coordinator,
            config_data, # Pass the correctly populated config_data
            f"{coordinator.area}_current_price",
            "Current Price",
            get_current_price, # Pass the function
            get_base_attrs     # Pass the function for additional attributes
        )
    )

    # Next hour price sensor
    entities.append(
        PriceValueSensor(
            coordinator,
            config_data, # Pass the correctly populated config_data
            f"{coordinator.area}_next_hour_price",
            "Next Hour Price",
            get_next_hour_price, # Pass the function
            None                 # No specific additional attributes needed here yet
        )
    )

    # Average price sensor
    entities.append(
        PriceStatisticSensor(
            coordinator,
            f"{coordinator.area}_average_price",
            "Average Price",
            "average",
            include_vat,
            vat,
            price_in_cents
        )
    )

    # Peak price sensor
    entities.append(
        ExtremaPriceSensor(
            coordinator,
            config_data, # Pass the correctly populated config_data
            f"{coordinator.area}_peak_price",
            "Peak Price",
            extrema_type="max" # Pass as keyword argument
        )
    )

    # Off-peak price sensor
    entities.append(
        ExtremaPriceSensor(
            coordinator,
            config_data, # Pass the correctly populated config_data
            f"{coordinator.area}_off_peak_price",
            "Off-Peak Price",
            extrema_type="min" # Pass as keyword argument
        )
    )

    # Off-peak/peak periods
    entities.append(
        OffPeakPeakSensor(
            coordinator,
            f"{coordinator.area}_peak_offpeak_prices",
            "Peak/Off-Peak Prices",
            include_vat,
            vat,
            price_in_cents
        )
    )

    # Price difference (current vs average)
    entities.append(
        PriceDifferenceSensor(
            coordinator,
            f"{coordinator.area}_price_difference",
            "Price Difference",
            "current_price",
            "average",
            include_vat,
            vat,
            price_in_cents
        )
    )

    # Price percentage (current vs average)
    entities.append(
        PricePercentSensor(
            coordinator,
            f"{coordinator.area}_price_percentage",
            "Price Percentage",
            "current_price",
            "average",
            include_vat,
            vat
        )
    )

    # Add all entities
    async_add_entities(entities)

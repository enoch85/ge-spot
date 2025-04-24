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

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get config options
    config = dict(config_entry.data)
    if config_entry.options:
        config.update(config_entry.options)

    # Get VAT setting
    vat = config.get(Config.VAT, 0) / 100  # Convert from percentage to decimal
    include_vat = config.get(Config.INCLUDE_VAT, False)
    currency = config.get(Config.CURRENCY, coordinator.currency)
    price_in_cents = config.get(Config.DISPLAY_UNIT) == "cents"
    
    # Create sensor entities
    sensors = []
    
    # Current price sensor
    sensors.append(
        PriceValueSensor(
            coordinator, 
            f"{coordinator.area}_current_price",
            "Current Price", 
            "current_price",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Next hour price sensor
    sensors.append(
        PriceValueSensor(
            coordinator, 
            f"{coordinator.area}_next_hour_price",
            "Next Hour Price", 
            "next_hour_price",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Average price sensor
    sensors.append(
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
    sensors.append(
        ExtremaPriceSensor(
            coordinator, 
            f"{coordinator.area}_peak_price",
            "Peak Price", 
            "max",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Off-peak price sensor
    sensors.append(
        ExtremaPriceSensor(
            coordinator, 
            f"{coordinator.area}_off_peak_price",
            "Off-Peak Price", 
            "min",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Off-peak/peak periods
    sensors.append(
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
    sensors.append(
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
    sensors.append(
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
    async_add_entities(sensors, True)

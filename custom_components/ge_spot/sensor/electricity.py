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

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the GE Spot electricity sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Create a proper config_data dictionary
    config_data = {
        "entry_id": config_entry.entry_id,
        # Add any other configuration data needed
    }
    
    entities = []
    
    # Get configuration settings from options flow
    options = config_entry.options
    
    # Get VAT setting
    vat = options.get(Config.VAT, 0) / 100  # Convert from percentage to decimal
    include_vat = options.get(Config.INCLUDE_VAT, False)
    currency = options.get(Config.CURRENCY, coordinator.currency)
    price_in_cents = options.get(Config.DISPLAY_UNIT) == "cents"
    
    # Create sensor entities
    
    # Current price sensor
    entities.append(
        PriceValueSensor(
            coordinator, 
            config_data,  # Now passing a dictionary
            f"{coordinator.area}_current_price",
            "Current Price", 
            "current_price",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Next hour price sensor
    entities.append(
        PriceValueSensor(
            coordinator, 
            config_data,
            f"{coordinator.area}_next_hour_price",
            "Next Hour Price", 
            "next_hour_price",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Average price sensor
    entities.append(
        PriceStatisticSensor(
            coordinator, 
            config_data,
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
            config_data,
            f"{coordinator.area}_peak_price",
            "Peak Price", 
            "max",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Off-peak price sensor
    entities.append(
        ExtremaPriceSensor(
            coordinator, 
            config_data,
            f"{coordinator.area}_off_peak_price",
            "Off-Peak Price", 
            "min",
            include_vat,
            vat,
            price_in_cents
        )
    )
    
    # Off-peak/peak periods
    entities.append(
        OffPeakPeakSensor(
            coordinator,
            config_data,
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
            config_data,
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
            config_data,
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

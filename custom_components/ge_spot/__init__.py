"""Integration for electricity spot prices."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_AREA,
    CONF_UPDATE_INTERVAL,
    CONF_CURRENCY,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import ElectricityPriceCoordinator

# Import API handlers (as needed based on source)
from .api.base import BaseEnergyAPI

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Get configuration
    source_type = entry.data.get(CONF_SOURCE)
    area = entry.data.get(CONF_AREA)
    currency = entry.data.get(CONF_CURRENCY)
    
    _LOGGER.debug(f"Setting up integration with source_type: {source_type}, area: {area}")
    
    if not source_type:
        _LOGGER.error(f"Invalid source type: {source_type}. Check your configuration.")
        raise ConfigEntryNotReady(f"Invalid source type: {source_type}")
    
    # Create API handler
    api = create_api_handler(source_type, entry.data, entry.options)
    
    if not api:
        _LOGGER.error(f"Failed to create API handler for source type: {source_type}")
        raise ConfigEntryNotReady(f"Failed to create API handler for source type: {source_type}")
    
    # Get update interval (prefer options over data, with fallback to default)
    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL, 
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
    
    # Create a data coordinator
    coordinator = ElectricityPriceCoordinator(
        hass,
        f"electricity_prices_{area}",
        timedelta(minutes=update_interval),
        api,
        area,
        currency,
    )
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store the coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Close API session
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.api.close()
    
    # Remove entry from data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

def create_api_handler(source_type, config, options=None):
    """Create the appropriate API handler based on source type."""
    # Implementation will vary based on your API modules
    # This is a placeholder for the actual implementation
    # You should import and return the appropriate API class instance
    return BaseEnergyAPI(config)

"""Integration for electricity spot prices."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    Config,
    Defaults,
    CONF_SOURCE,
    CONF_AREA,
    CONF_UPDATE_INTERVAL,
    CONF_CURRENCY,
    CONF_ENABLE_FALLBACK,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ENABLE_FALLBACK,
    REGION_TO_CURRENCY,
)
from .coordinator import ElectricityPriceCoordinator
from .api import create_api, get_fallback_apis

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Get configuration
    source_type = entry.data.get(Config.SOURCE)
    area = entry.data.get(Config.AREA)
    
    # Get currency based on region
    currency = entry.data.get(Config.CURRENCY, REGION_TO_CURRENCY.get(area, "EUR"))
    
    _LOGGER.debug(f"Setting up integration with source_type: {source_type}, area: {area}, currency: {currency}")
    
    if not source_type:
        _LOGGER.error(f"Invalid source type: {source_type}. Check your configuration.")
        raise ConfigEntryNotReady(f"Invalid source type: {source_type}")
    
    # Create config dict combining data and options
    config = dict(entry.data)
    if entry.options:
        config.update(entry.options)
    
    # Create API handler using factory
    api = await hass.async_add_executor_job(create_api, source_type, config)
    
    if not api:
        _LOGGER.error(f"Failed to create API handler for source type: {source_type}")
        raise ConfigEntryNotReady(f"Failed to create API handler for source type: {source_type}")
    
    # Get update interval (prefer options over data, with fallback to default)
    update_interval = entry.options.get(
        Config.UPDATE_INTERVAL, 
        entry.data.get(Config.UPDATE_INTERVAL, Defaults.UPDATE_INTERVAL)
    )
    
    # Check if fallback is enabled
    enable_fallback = entry.options.get(
        Config.ENABLE_FALLBACK,
        entry.data.get(Config.ENABLE_FALLBACK, Defaults.ENABLE_FALLBACK)
    )
    
    # Get fallback APIs if enabled
    fallback_apis = []
    if enable_fallback:
        fallback_apis = await hass.async_add_executor_job(
            get_fallback_apis, source_type, config
        )
        if fallback_apis:
            _LOGGER.debug(f"Created {len(fallback_apis)} fallback API handlers")
    
    # Create a data coordinator
    coordinator = ElectricityPriceCoordinator(
        hass,
        f"electricity_prices_{area}",
        timedelta(minutes=update_interval),
        api,
        area,
        currency,
        fallback_apis,
        enable_fallback,
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
    
    # Close fallback API sessions if they exist
    if hasattr(coordinator, '_fallback_apis'):
        for fallback_api in coordinator._fallback_apis:
            await fallback_api.close()
    
    # Remove entry from data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

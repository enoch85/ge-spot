import logging
import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_NORDPOOL,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import GSpotDataUpdateCoordinator

# Import API handlers
from .api.energi_data import EnergiDataServiceAPI
from .api.nordpool import NordpoolAPI

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Get configuration
    source_type = entry.data.get(CONF_SOURCE)
    
    _LOGGER.debug(f"Setting up integration with source_type: {source_type}")
    _LOGGER.debug(f"Config entry data: {entry.data}")
    
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
    coordinator = GSpotDataUpdateCoordinator(
        hass,
        api,
        update_interval,
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
    # Merge config and options, with options taking precedence
    combined_config = dict(config)
    if options:
        combined_config.update(options)
    
    _LOGGER.debug(f"Creating API handler for source_type: {source_type}")
    
    if source_type == SOURCE_ENERGI_DATA_SERVICE:
        return EnergiDataServiceAPI(combined_config)
    elif source_type == SOURCE_NORDPOOL:
        return NordpoolAPI(combined_config)
    elif source_type == SOURCE_ENTSO_E:
        # Import here to avoid circular imports
        from .api.entsoe import EntsoEAPI
        return EntsoEAPI(combined_config)
    elif source_type == SOURCE_EPEX:
        from .api.epex import EpexAPI
        return EpexAPI(combined_config)
    elif source_type == SOURCE_OMIE:
        from .api.omie import OmieAPI
        return OmieAPI(combined_config)
    elif source_type == SOURCE_AEMO:
        from .api.aemo import AemoAPI
        return AemoAPI(combined_config)
    else:
        _LOGGER.error(f"Unknown source type: {source_type}")
        return None

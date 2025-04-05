"""Integration for electricity spot prices."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_AREA,
    CONF_UPDATE_INTERVAL,
    CONF_CURRENCY,
    DEFAULT_UPDATE_INTERVAL,
    REGION_TO_CURRENCY,
)
from .coordinator import RegionPriceCoordinator
from .api.base import register_shutdown_task

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Get configuration
    area = entry.data.get(CONF_AREA)

    # Get currency based on region
    currency = entry.data.get(CONF_CURRENCY, REGION_TO_CURRENCY.get(area, "EUR"))

    _LOGGER.debug(f"Setting up integration for area: {area}, currency: {currency}")

    if not area:
        _LOGGER.error(f"Invalid area: {area}. Check your configuration.")
        raise ConfigEntryNotReady(f"Invalid area: {area}")

    # Create config dict combining data and options
    config = dict(entry.data)
    if entry.options:
        config.update(entry.options)

    # Get update interval (prefer options over data, with fallback to default)
    # Convert update interval to integer to avoid TypeError
    update_interval = int(entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    ))

    # Create a data coordinator
    coordinator = RegionPriceCoordinator(
        hass,
        area,
        currency,
        timedelta(minutes=update_interval),
        config,
    )

    # Register shutdown task to close all sessions when Home Assistant stops
    register_shutdown_task(hass)

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

    # Close API sessions
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_close()

    # Remove entry from data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

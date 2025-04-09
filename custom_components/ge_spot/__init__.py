"""Integration for electricity spot prices."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, Config, Defaults
from .price.currency import get_default_currency
from .coordinator.region import RegionPriceCoordinator
from .api.base.session_manager import register_shutdown_task

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    area = entry.data.get(Config.AREA)
    currency = entry.data.get(Config.CURRENCY, get_default_currency(area))
    
    _LOGGER.debug(f"Setting up integration for area: {area}, currency: {currency}")

    if not area:
        _LOGGER.error(f"Invalid area: {area}. Check your configuration.")
        raise ConfigEntryNotReady(f"Invalid area: {area}")

    # Create config dict combining data and options
    config = dict(entry.data)
    if entry.options:
        config.update(entry.options)

    # Get update interval (prefer options over data, with fallback to default)
    update_interval = int(entry.options.get(
        Config.UPDATE_INTERVAL,
        entry.data.get(Config.UPDATE_INTERVAL, Defaults.UPDATE_INTERVAL)
    ))

    coordinator = RegionPriceCoordinator(hass, area, currency, timedelta(minutes=update_interval), config)
    register_shutdown_task(hass)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

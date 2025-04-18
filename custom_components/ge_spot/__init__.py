"""Integration for electricity spot prices."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

# Define CONFIG_SCHEMA to fix the warning
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
from .const.config import Config
from .const.defaults import Defaults
from .const.network import Network
from .price.currency import get_default_currency
from .coordinator.region import RegionPriceCoordinator
from .api.base.session_manager import register_shutdown_task
from .utils.exchange_service import get_exchange_service

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config):  # pylint: disable=unused-argument
    """Set up the GE-Spot component."""
    # Initialize exchange rate service and register update handlers
    exchange_service = await get_exchange_service()
    exchange_service.register_update_handlers(hass)

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    area = entry.data.get(Config.AREA)
    currency = entry.data.get(Config.CURRENCY, get_default_currency(area))

    _LOGGER.debug("Setting up integration for area: %s, currency: %s", area, currency)

    if not area:
        _LOGGER.error("Invalid area: %s. Check your configuration.", area)
        raise ConfigEntryNotReady(f"Invalid area: {area}")

    # Create config dict combining data and options
    config = dict(entry.data)
    if entry.options:
        config.update(entry.options)

    # Use a placeholder update interval - the coordinator will determine the actual interval
    # based on the source-specific intervals defined in SourceIntervals
    update_interval = Defaults.UPDATE_INTERVAL

    coordinator = RegionPriceCoordinator(
        hass, area, currency, timedelta(minutes=update_interval), config
    )
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

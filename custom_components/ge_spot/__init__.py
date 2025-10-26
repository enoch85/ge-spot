"""Integration for electricity spot prices."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .const.config import Config
from .const.defaults import Defaults
from .coordinator import UnifiedPriceCoordinator  # Import only the new coordinator
from .api.base.session_manager import register_shutdown_task
from .utils.exchange_service import get_exchange_service
from .price.currency_service import get_default_currency

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

# This integration is config-entry only (configured via UI, not YAML)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# UnifiedPriceCoordinator is the sole supported approach; legacy coordinator has been removed.


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

    # Always use UnifiedPriceCoordinator - remove legacy coordinator completely
    _LOGGER.info(f"Using UnifiedPriceCoordinator for area {area}")
    coordinator = UnifiedPriceCoordinator(
        hass, area, currency, timedelta(minutes=update_interval), config
    )

    register_shutdown_task(hass)

    # Always run first_refresh to ensure sensors have data before creation
    # fetch_data() will validate sources implicitly and use fallback if needed
    try:
        await coordinator.async_config_entry_first_refresh()

        # Schedule health check task in background (fully non-blocking)
        # The task itself will run immediate validation, then continue daily schedule
        if not coordinator.price_manager._health_check_scheduled:
            _LOGGER.info(f"Scheduling health check task for {area}")
            asyncio.create_task(
                coordinator.price_manager._schedule_health_check(run_immediately=True)
            )
            coordinator.price_manager._health_check_scheduled = True

    except Exception as e:
        _LOGGER.error(
            f"First refresh failed for {area}: {e}. "
            f"Sensor will be unavailable until next update cycle."
        )
        # Don't block HA boot - coordinator will retry on next interval

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

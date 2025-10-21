"""Config flow for GE-Spot integration."""

import logging

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from ..const import DOMAIN
from .implementation import GSpotConfigFlow
from .options import GSpotOptionsFlow

_LOGGER = logging.getLogger(__name__)


# This ensures the implementation of ConfigFlow is imported and used
async def async_get_options_flow(config_entry):
    """Get the options flow for this handler."""
    return GSpotOptionsFlow(config_entry)

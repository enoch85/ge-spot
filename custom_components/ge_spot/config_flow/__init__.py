"""Config flow for GE-Spot integration."""

import logging

from .implementation import GSpotConfigFlow  # noqa: F401
from .options import GSpotOptionsFlow

_LOGGER = logging.getLogger(__name__)


# This ensures the implementation of ConfigFlow is imported and used
async def async_get_options_flow(config_entry):
    """Get the options flow for this handler."""
    return GSpotOptionsFlow(config_entry)

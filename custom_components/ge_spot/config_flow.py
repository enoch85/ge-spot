"""Config flow for GE-Spot integration."""
import logging
from typing import Dict, Any, Optional
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN
from .config_flow.base import GSpotConfigFlowBase
from .config_flow.options import GSpotOptionsFlow

_LOGGER = logging.getLogger(__name__)

class GSpotConfigFlow(GSpotConfigFlowBase, domain=DOMAIN):
    """Handle a config flow for GE-Spot integration."""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GSpotOptionsFlow(config_entry)

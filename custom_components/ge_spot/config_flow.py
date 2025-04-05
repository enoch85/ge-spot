"""Config flow for GE-Spot integration."""
import logging
from typing import Dict, Any, Optional
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .config_flow.base import GSpotConfigFlowBase
from .config_flow.options import GSpotOptionsFlow

_LOGGER = logging.getLogger(__name__)

class GSpotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GE-Spot integration."""
    VERSION = 1
    CONNECTION_CLASS = "cloud_poll"

    def __init__(self):
        """Initialize the config flow."""
        super().__init__()
        self._data = {}
        self._supported_sources = []

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        return await GSpotConfigFlowBase.async_step_user(self, user_input)

    async def async_step_source_priority(self, user_input=None) -> FlowResult:
        """Handle setting source priorities."""
        return await GSpotConfigFlowBase.async_step_source_priority(self, user_input)

    async def async_step_api_keys(self, user_input=None) -> FlowResult:
        """Handle API key entry for sources that require it."""
        return await GSpotConfigFlowBase.async_step_api_keys(self, user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GSpotOptionsFlow(config_entry)

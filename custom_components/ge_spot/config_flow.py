"""Config flow for GE-Spot integration."""
from .config_flow.implementation import GSpotConfigFlow, GSpotOptionsFlow  # pylint: disable=unused-import

# Home Assistant expects to find ConfigFlow class in this file
# Re-export as ConfigFlow for Home Assistant to discover
ConfigFlow = GSpotConfigFlow

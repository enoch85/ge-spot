"""Config flow for GE-Spot integration."""

from .config_flow.implementation import GSpotConfigFlow
from .config_flow.options import GSpotOptionsFlow

# Expose config flow classes at module level for Home Assistant discovery
__all__ = ["GSpotConfigFlow", "GSpotOptionsFlow"]

"""Config flow for GE-Spot integration.

Home Assistant discovers the config flow by importing this package, which
registers ``GSpotConfigFlow`` via its ``domain=DOMAIN`` class definition. The
options flow is provided by ``GSpotConfigFlow.async_get_options_flow`` (a
staticmethod), so no module-level handler is needed here.
"""

from .implementation import GSpotConfigFlow
from .options import GSpotOptionsFlow

__all__ = ["GSpotConfigFlow", "GSpotOptionsFlow"]

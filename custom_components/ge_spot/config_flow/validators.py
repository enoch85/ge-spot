"""Validation functions for config flow."""
import logging
import datetime

from ..const.areas import AreaMapping
from ..const.sources import Source
from ..api import create_api

_LOGGER = logging.getLogger(__name__)

async def validate_entsoe_api_key(api_key, area, session=None):
    """Validate an ENTSO-E API key by making a test request."""
    try:
        # Create a temporary API instance
        config = {
            "area": area,
            "api_key": api_key
        }
        api = create_api(Source.ENTSOE, config)

        # Use provided session if available
        if session:
            api.session = session
            api._owns_session = False

        # Try to fetch some data with the provided key
        _LOGGER.debug(f"Validating ENTSO-E API key for area {area}")
        result = await api._fetch_data()

        # Close session if we created one
        if hasattr(api, '_owns_session') and api._owns_session and hasattr(api, 'close'):
            await api.close()

        # Check if we got a valid response
        if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
            _LOGGER.debug("ENTSO-E API key validation successful")
            return True
        elif isinstance(result, str) and "Not authorized" in result:
            _LOGGER.error("API key validation failed: Not authorized")
            return False
        elif isinstance(result, str) and "No matching data found" in result:
            # This is technically a valid API key, even if there's no data
            _LOGGER.warning("API key is valid but no data available for the specified area")
            return True
        else:
            _LOGGER.error("API key validation failed: No valid data returned")
            return False

    except Exception as e:
        _LOGGER.error(f"API key validation error: {e}")
        return False

def get_entso_e_api_key_description(area):
    """Get description for ENTSO-E API key entry."""
    is_supported = area in AreaMapping.ENTSOE_MAPPING
    # Show different message based on whether area is directly supported
    description = (
        "Optional API key for ENTSO-E (recommended for better reliability)"
        if is_supported else
        "Required API key for ENTSO-E (needed for this region)"
    )

    return description

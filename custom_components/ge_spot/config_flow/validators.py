"""Validation functions for config flow."""
import logging
import datetime
from typing import Dict, List

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


def validate_area_sources(area: str, available_sources: List[str]) -> Dict[str, str]:
    """Validate that area has at least one working source.
    
    Args:
        area: Area code
        available_sources: List of available sources for this area
    
    Returns:
        Dictionary of errors (empty if valid)
    """
    errors = {}
    
    if not available_sources:
        errors["area"] = "no_sources_available"
        _LOGGER.error(f"Area {area} has no available sources")
        return errors
    
    # Check for areas with only ENTSOE that don't have EIC codes
    if len(available_sources) == 1 and Source.ENTSOE in available_sources:
        if area not in AreaMapping.ENTSOE_MAPPING:
            errors["area"] = "entsoe_no_eic_code"
            _LOGGER.error(
                f"Area {area} only has ENTSOE available but no EIC code mapping. "
                f"This area cannot be configured."
            )
    
    return errors


def validate_source_availability(area: str, source: str) -> bool:
    """Check if a source is actually available for an area.
    
    Args:
        area: Area code
        source: Source identifier
    
    Returns:
        True if source can work for this area
    """
    if source == Source.ENTSOE:
        return area in AreaMapping.ENTSOE_MAPPING
    
    if source == Source.NORDPOOL:
        return area in AreaMapping.NORDPOOL_AREAS
    
    if source == Source.ENERGY_CHARTS:
        return area in AreaMapping.ENERGY_CHARTS_BZN
    
    if source == Source.ENERGI_DATA_SERVICE:
        return area in AreaMapping.ENERGI_DATA_AREAS
    
    if source == Source.OMIE:
        return area in AreaMapping.OMIE_AREAS
    
    if source == Source.AEMO:
        return area in AreaMapping.AEMO_AREAS
    
    if source == Source.STROMLIGNING:
        return area in AreaMapping.STROMLIGNING_AREAS
    
    if source == Source.COMED:
        return area in AreaMapping.COMED_AREAS
    
    return False

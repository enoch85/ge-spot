"""Validation functions for config flow."""

import logging
from typing import Dict, List

from ..const.areas import AreaMapping
from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)


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

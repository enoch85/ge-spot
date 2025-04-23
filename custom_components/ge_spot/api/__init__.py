"""API module for the GE-Spot integration."""
import logging
from typing import List

from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)

def get_sources_for_region(region: str) -> List[str]:
    """Get available sources for a region."""
    from ..const.areas import get_available_sources
    return get_available_sources(region)

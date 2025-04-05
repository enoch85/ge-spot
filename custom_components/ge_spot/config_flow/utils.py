"""Utility functions for config flow."""
import logging
from typing import Dict, Set, List

from ..const import (
    SOURCE_NORDPOOL,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
    NORDPOOL_AREAS,
    ENERGI_DATA_AREAS,
    ENTSOE_AREAS,
    EPEX_AREAS,
    OMIE_AREAS,
    AEMO_AREAS,
)
from ..api import get_sources_for_region

_LOGGER = logging.getLogger(__name__)

# Define a list of API sources in priority order for UI display
API_SOURCE_PRIORITIES = [
    SOURCE_NORDPOOL,      # Highest priority
    SOURCE_ENTSO_E,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO           # Lowest priority
]

# Mapping of source to area dictionaries
SOURCE_AREA_MAPS = {
    SOURCE_NORDPOOL: NORDPOOL_AREAS,
    SOURCE_ENERGI_DATA_SERVICE: ENERGI_DATA_AREAS,
    SOURCE_ENTSO_E: ENTSOE_AREAS,
    SOURCE_EPEX: EPEX_AREAS,
    SOURCE_OMIE: OMIE_AREAS,
    SOURCE_AEMO: AEMO_AREAS,
}

# Mapping of which source supports which regions
SOURCE_REGION_SUPPORT = {
    SOURCE_NORDPOOL: set(NORDPOOL_AREAS.keys()),
    SOURCE_ENERGI_DATA_SERVICE: set(ENERGI_DATA_AREAS.keys()),
    SOURCE_ENTSO_E: set(ENTSOE_AREAS.keys()),
    SOURCE_EPEX: set(EPEX_AREAS.keys()),
    SOURCE_OMIE: set(OMIE_AREAS.keys()),
    SOURCE_AEMO: set(AEMO_AREAS.keys()),
}

# Source reliability ratings (higher is better)
SOURCE_RELIABILITY = {
    SOURCE_NORDPOOL: 10,  # Most reliable
    SOURCE_ENERGI_DATA_SERVICE: 8,
    SOURCE_ENTSO_E: 7,
    SOURCE_EPEX: 7,
    SOURCE_OMIE: 6,
    SOURCE_AEMO: 6,
}

def get_deduplicated_regions():
    """Get a deduplicated list of regions by display name."""
    # 1. Create a mapping of display_name → list of region info tuples
    display_name_map = {}

    # First, collect all regions from all sources
    for source, area_dict in SOURCE_AREA_MAPS.items():
        source_priority = API_SOURCE_PRIORITIES.index(source) if source in API_SOURCE_PRIORITIES else 999
        for region_code, display_name in area_dict.items():
            # Normalize display name to handle different capitalizations
            normalized_name = display_name.lower()
            if normalized_name not in display_name_map:
                display_name_map[normalized_name] = []
            # Store tuple of (source_priority, region_code, display_name, source)
            display_name_map[normalized_name].append((
                source_priority, region_code, display_name, source
            ))

    # 2. Now create a deduplicated regions dictionary
    deduplicated_regions = {}
    for name_variants in display_name_map.values():
        # Sort by source priority (lower number = higher priority)
        sorted_variants = sorted(name_variants)
        # Choose the preferred region code based on source priority
        for priority, region_code, display_name, source in sorted_variants:
            try:
                # Only include if the region is supported by at least one API
                supported_sources = get_sources_for_region(region_code)
                if supported_sources:
                    deduplicated_regions[region_code] = display_name
                    break
            except Exception as e:
                _LOGGER.error(f"Error checking sources for region {region_code}: {e}")
                # Continue to next variant rather than fail completely
                continue

    _LOGGER.debug(f"Deduplicated regions: {deduplicated_regions}")
    return deduplicated_regions

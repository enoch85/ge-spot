"""Utility functions for config flow."""
import logging

from ..const.sources import Source
from ..const.areas import AreaMapping
from ..api import get_sources_for_region

_LOGGER = logging.getLogger(__name__)

# Mapping of source to area dictionaries for convenience
SOURCE_AREA_MAPS = {
    Source.NORDPOOL: AreaMapping.NORDPOOL_AREAS,
    Source.ENERGI_DATA_SERVICE: AreaMapping.ENERGI_DATA_AREAS,
    Source.ENTSOE: AreaMapping.ENTSOE_AREAS,
    Source.EPEX: AreaMapping.EPEX_AREAS,
    Source.OMIE: AreaMapping.OMIE_AREAS,
    Source.AEMO: AreaMapping.AEMO_AREAS,
    Source.STROMLIGNING: AreaMapping.STROMLIGNING_AREAS,
    Source.COMED: AreaMapping.COMED_AREAS,
}

# Define a list of API sources in priority order for UI display
API_SOURCE_PRIORITIES = [
    Source.NORDPOOL,      # Highest priority
    Source.ENTSOE,
    Source.ENERGI_DATA_SERVICE,
    Source.EPEX,
    Source.OMIE,
    Source.STROMLIGNING,
    Source.AEMO,
    Source.COMED          # Lowest priority
]

def get_deduplicated_regions():
    """Get a deduplicated list of regions by display name."""
    # Create a mapping of display_name → list of region info tuples
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

    # Now create a deduplicated regions dictionary
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

    _LOGGER.debug(f"Deduplicated regions: {len(deduplicated_regions)} entries")
    return deduplicated_regions

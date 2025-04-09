"""API modules for the energy prices integration."""
import logging
from typing import Dict, Optional, List, Any

from ..const import (
    Source,
    AreaMapping
)

_LOGGER = logging.getLogger(__name__)

# Mapping of sources to supported regions
SOURCE_REGION_SUPPORT = {
    Source.NORDPOOL: set(AreaMapping.NORDPOOL_AREAS.keys()),
    Source.ENERGI_DATA_SERVICE: set(AreaMapping.ENERGI_DATA_AREAS.keys()),
    Source.ENTSO_E: set(AreaMapping.ENTSOE_AREAS.keys()),
    Source.EPEX: set(AreaMapping.EPEX_AREAS.keys()),
    Source.OMIE: set(AreaMapping.OMIE_AREAS.keys()),
    Source.AEMO: set(AreaMapping.AEMO_AREAS.keys()),
    Source.STROMLIGNING: set(AreaMapping.STROMLIGNING_AREAS.keys()),
}

# Source reliability ratings (higher is better)
SOURCE_RELIABILITY = {
    Source.NORDPOOL: 10,
    Source.ENERGI_DATA_SERVICE: 8,
    Source.ENTSO_E: 7,
    Source.EPEX: 7,
    Source.OMIE: 6,
    Source.AEMO: 6,
    Source.STROMLIGNING: 8,
}

class ApiRegistry:
    """Registry for API handlers with region-based discovery."""

    def __init__(self):
        """Initialize the registry."""
        self._apis = {}

    def register(self, source_type: str, api_module):
        """Register an API module for a source type."""
        self._apis[source_type] = api_module

    async def fetch_prices(self, source_type: str, config: dict, area: str, currency: str, 
                          reference_time=None, hass=None):
        """Fetch prices from a specific API."""
        api_module = self._apis.get(source_type)
        if not api_module:
            _LOGGER.error(f"Unknown source type: {source_type}")
            return None

        try:
            # Make a copy of the config with area set
            config_with_area = dict(config)
            config_with_area["area"] = area
            
            return await api_module.fetch_day_ahead_prices(
                config_with_area, area, currency, reference_time, hass, config.get("session")
            )
        except Exception as e:
            _LOGGER.error(f"Error fetching prices from {source_type}: {e}")
            return None

    def get_sources_for_region(self, region: str) -> List[str]:
        """Get list of sources that support a given region, ordered by reliability."""
        supported_sources = []

        for source, regions in SOURCE_REGION_SUPPORT.items():
            if region in regions:
                supported_sources.append(source)

        # Sort by reliability (highest first)
        return sorted(supported_sources,
                    key=lambda s: SOURCE_RELIABILITY.get(s, 0),
                    reverse=True)

    async def create_apis_for_region(self, region: str, config: dict,
                                   currency: str, reference_time=None, hass=None,
                                   source_priority: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Create API instances for all sources supporting a region."""
        if source_priority:
            # Use custom priority order
            sources = [s for s in source_priority if region in SOURCE_REGION_SUPPORT.get(s, set())]
        else:
            # Use default order by reliability
            sources = self.get_sources_for_region(region)

        _LOGGER.debug(f"Fetching prices for region {region} with priority: {sources}")

        results = []
        for source in sources:
            data = await self.fetch_prices(source, config, region, currency, reference_time, hass)
            if data:
                data["source"] = source
                data["fallback_used"] = sources[0] != source
                results.append(data)

        return results

    def get_fallback_chain(self, primary_source: str, area: str) -> List[str]:
        """Get list of fallback sources for a primary source."""
        # Define fallback chain based on region compatibility
        fallback_map = {
            Source.NORDPOOL: [Source.ENERGI_DATA_SERVICE, Source.ENTSO_E, Source.EPEX],
            Source.ENERGI_DATA_SERVICE: [Source.NORDPOOL, Source.ENTSO_E],
            Source.ENTSO_E: [Source.NORDPOOL, Source.EPEX],
            Source.EPEX: [Source.ENTSO_E, Source.NORDPOOL],
            Source.OMIE: [Source.ENTSO_E],
            Source.AEMO: [],  # No fallbacks for AEMO currently
            Source.STROMLIGNING: [Source.ENERGI_DATA_SERVICE, Source.NORDPOOL],
        }

        # Get fallback sources for this primary source
        fallbacks = fallback_map.get(primary_source, [])
        
        # Filter to only include sources that support this area
        return [s for s in fallbacks if area in SOURCE_REGION_SUPPORT.get(s, set())]

# Global registry
registry = ApiRegistry()

def register_apis():
    """Register all available API handlers."""
    # Import APIs
    from . import nordpool
    from . import energi_data
    from . import entsoe
    from . import epex
    from . import omie
    from . import aemo
    from . import stromligning

    # Register all APIs
    registry.register(Source.NORDPOOL, nordpool)
    registry.register(Source.ENERGI_DATA_SERVICE, energi_data)
    registry.register(Source.ENTSO_E, entsoe)
    registry.register(Source.EPEX, epex)
    registry.register(Source.OMIE, omie)
    registry.register(Source.AEMO, aemo)
    registry.register(Source.STROMLIGNING, stromligning)

# Register APIs on module import
register_apis()

async def fetch_day_ahead_prices(source_type: str, config: dict, area: str, currency: str, 
                               reference_time=None, hass=None):
    """Fetch prices from a specific API."""
    return await registry.fetch_prices(source_type, config, area, currency, reference_time, hass)

def get_sources_for_region(region: str) -> List[str]:
    """Get sources supporting a region in priority order."""
    return registry.get_sources_for_region(region)

async def create_apis_for_region(region: str, config: dict, 
                               source_priority: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Create API instances for all sources supporting a region."""
    currency = config.get("currency", "EUR")
    return await registry.create_apis_for_region(
        region, config, currency, None, None, source_priority
    )

def get_fallback_chain(primary_source: str, area: str) -> List[str]:
    """Get list of fallback sources for a primary source."""
    return registry.get_fallback_chain(primary_source, area)

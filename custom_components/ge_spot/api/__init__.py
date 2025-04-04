"""API modules for the energy prices integration."""
import logging
from typing import Dict, Optional, Type, List, Set

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

_LOGGER = logging.getLogger(__name__)

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

class ApiRegistry:
    """Registry for API handlers with region-based discovery."""

    def __init__(self):
        """Initialize the registry."""
        self._apis = {}

    def register(self, source_type: str, api_class):
        """Register an API class for a source type."""
        self._apis[source_type] = api_class

    def create(self, source_type: str, config: dict):
        """Create an API instance."""
        api_class = self._apis.get(source_type)
        if not api_class:
            _LOGGER.error(f"Unknown source type: {source_type}")
            return None

        try:
            return api_class(config)
        except Exception as e:
            _LOGGER.error(f"Error creating API instance for {source_type}: {e}")
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
                
    def create_apis_for_region(self, region: str, config: dict, 
                            source_priority: Optional[List[str]] = None) -> List:
        """Create API instances for all sources supporting a region.
        
        Args:
            region: The region code
            config: Configuration dictionary
            source_priority: Optional custom source priority order
            
        Returns:
            List of API instances in priority order
        """
        if source_priority:
            # Use custom priority order
            sources = [s for s in source_priority if region in SOURCE_REGION_SUPPORT.get(s, set())]
        else:
            # Use default order by reliability
            sources = self.get_sources_for_region(region)

        _LOGGER.debug(f"Creating APIs for region {region} with priority: {sources}")

        # Create a copy of the config with the area set
        config_with_area = dict(config)
        config_with_area["area"] = region
            
        apis = []
        for source in sources:
            api = self.create(source, config_with_area)
            if api:
                apis.append(api)
                
        return apis

# Global registry
registry = ApiRegistry()

def register_apis():
    """Register all available API handlers."""
    # Import here to avoid circular imports
    from .nordpool import NordpoolAPI
    from .energi_data import EnergiDataServiceAPI
    from .entsoe import EntsoEAPI
    from .epex import EpexAPI
    from .omie import OmieAPI
    from .aemo import AemoAPI

    # Register all APIs
    registry.register(SOURCE_NORDPOOL, NordpoolAPI)
    registry.register(SOURCE_ENERGI_DATA_SERVICE, EnergiDataServiceAPI)
    registry.register(SOURCE_ENTSO_E, EntsoEAPI)
    registry.register(SOURCE_EPEX, EpexAPI)
    registry.register(SOURCE_OMIE, OmieAPI)
    registry.register(SOURCE_AEMO, AemoAPI)

# Register APIs on module import
register_apis()

def create_api(source_type: str, config: dict):
    """Create an API instance."""
    return registry.create(source_type, config)

def get_sources_for_region(region: str) -> List[str]:
    """Get sources supporting a region in priority order."""
    return registry.get_sources_for_region(region)
    
def create_apis_for_region(region: str, config: dict, 
                        source_priority: Optional[List[str]] = None) -> List:
    """Create prioritized API instances for a region."""
    return registry.create_apis_for_region(region, config, source_priority)

def get_fallback_apis(primary_source: str, config: dict):
    """Get list of fallback API instances for a primary source."""
    fallbacks = []

    # Define fallback chain based on region compatibility
    fallback_map = {
        SOURCE_NORDPOOL: [SOURCE_ENERGI_DATA_SERVICE, SOURCE_ENTSO_E, SOURCE_EPEX],
        SOURCE_ENERGI_DATA_SERVICE: [SOURCE_NORDPOOL, SOURCE_ENTSO_E],
        SOURCE_ENTSO_E: [SOURCE_NORDPOOL, SOURCE_EPEX],
        SOURCE_EPEX: [SOURCE_ENTSO_E, SOURCE_NORDPOOL],
        SOURCE_OMIE: [SOURCE_ENTSO_E],
        SOURCE_AEMO: [],  # No fallbacks for AEMO currently
    }

    # Get fallback sources for this primary source
    fallback_sources = fallback_map.get(primary_source, [])

    # Create API instances for each fallback source
    for source in fallback_sources:
        fallback_api = registry.create(source, config)
        if fallback_api:
            fallbacks.append(fallback_api)

    return fallbacks

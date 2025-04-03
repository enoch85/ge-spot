"""API modules for the energy prices integration."""
import logging
from typing import Dict, Optional, Type

from ..const import (
    SOURCE_NORDPOOL,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
)

_LOGGER = logging.getLogger(__name__)

class ApiRegistry:
    """Registry for API handlers."""
    
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

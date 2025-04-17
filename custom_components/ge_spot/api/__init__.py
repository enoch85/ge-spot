"""API modules for the energy prices integration."""
import logging
from typing import Dict, Optional, List, Any

from ..const.sources import Source
from ..const.areas import AreaMapping
from .base.data_fetch import is_skipped_response
# Import APIs
from . import nordpool
from . import energi_data
from . import entsoe
from . import epex
from . import omie
from . import aemo
from . import stromligning
from . import comed

_LOGGER = logging.getLogger(__name__)

# Mapping of sources to supported regions
SOURCE_REGION_SUPPORT = {
    Source.NORDPOOL: set(AreaMapping.NORDPOOL_AREAS.keys()),
    Source.ENERGI_DATA_SERVICE: set(AreaMapping.ENERGI_DATA_AREAS.keys()),
    Source.ENTSOE: set(AreaMapping.ENTSOE_AREAS.keys()),
    Source.EPEX: set(AreaMapping.EPEX_AREAS.keys()),
    Source.OMIE: set(AreaMapping.OMIE_AREAS.keys()),
    Source.AEMO: set(AreaMapping.AEMO_AREAS.keys()),
    Source.STROMLIGNING: set(AreaMapping.STROMLIGNING_AREAS.keys()),
    Source.COMED: set(AreaMapping.COMED_AREAS.keys()),
}

# Source reliability ratings (higher is better)
SOURCE_RELIABILITY = {
    Source.NORDPOOL: 10,
    Source.ENERGI_DATA_SERVICE: 8,
    Source.ENTSOE: 7,
    Source.EPEX: 7,
    Source.OMIE: 6,
    Source.AEMO: 6,
    Source.STROMLIGNING: 8,
    Source.COMED: 3,
}

class ApiRegistry:
    """Registry for API handlers with region-based discovery."""

    def __init__(self):
        """Initialize the registry."""
        self._apis = {}

    def register(self, source_type: str, api_module):
        """Register an API module for a source type."""
        self._apis[source_type] = api_module

    async def fetch_prices(
        self, source_type: str, config: dict, area: str, currency: str,
        reference_time=None, hass=None, session=None
    ):  # pylint: disable=too-many-arguments
        """Fetch prices from a specific API."""
        api_module = self._apis.get(source_type)
        if not api_module:
            _LOGGER.error("Unknown source type: %s", source_type)
            return None

        try:
            # Make a copy of the config with area set
            config_with_area = dict(config)
            config_with_area["area"] = area

            result = await api_module.fetch_day_ahead_prices(
                source_type, config_with_area, area, currency, reference_time, hass, session
            )

            # Check if the API was skipped due to missing credentials
            if is_skipped_response(result):
                reason = result.get('reason', 'unknown reason') if isinstance(result, dict) else 'unknown reason'
                _LOGGER.debug(f"API {source_type} skipped: {reason}")
                return result

            # If the result is None, it means the API call failed
            # Return None to indicate that we should try the next source
            if result is None:
                return None

            return result
        except ValueError as e:
            _LOGGER.error("Timezone error fetching prices from %s: %s", source_type, e)
            return None
        except Exception as e:
            _LOGGER.error("Error fetching prices from %s: %s", source_type, e)
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

    async def create_apis_for_region(
        self, region: str, config: dict, currency: str, reference_time=None,
        hass=None, source_priority: Optional[List[str]] = None, session=None
    ) -> List[Dict[str, Any]]:  # pylint: disable=too-many-arguments
        """Create API instances for all sources supporting a region."""
        if source_priority:
            # Use custom priority order
            sources = [s for s in source_priority if region in SOURCE_REGION_SUPPORT.get(s, set())]
        else:
            # Use default order by reliability
            sources = self.get_sources_for_region(region)

        _LOGGER.debug("Fetching prices for region %s with priority: %s", region, sources)

        results = []
        for source in sources:
            data = await self.fetch_prices(source, config, region, currency, reference_time, hass, session)
            if data:
                data["source"] = source
                data["fallback_used"] = sources[0] != source
                results.append(data)

        return results

    def get_fallback_chain(self, primary_source: str, area: str) -> List[str]:
        """Get list of fallback sources for a primary source."""
        # Define fallback chain based on region compatibility
        fallback_map = {
    Source.NORDPOOL: [Source.ENERGI_DATA_SERVICE, Source.ENTSOE, Source.EPEX],
    Source.ENERGI_DATA_SERVICE: [Source.NORDPOOL, Source.ENTSOE],
    Source.ENTSOE: [Source.NORDPOOL, Source.EPEX],
    Source.EPEX: [Source.ENTSOE, Source.NORDPOOL],
    Source.OMIE: [Source.ENTSOE],
            # AEMO can use other sources as fallbacks for missing hours
            # We'll try any other sources that support the same area
            Source.AEMO: [],  # Will be dynamically populated based on area support
            Source.STROMLIGNING: [Source.ENERGI_DATA_SERVICE, Source.NORDPOOL],
        }

        # Get fallback sources for this primary source
        fallbacks = fallback_map.get(primary_source, [])

        # Special handling for AEMO - dynamically find other sources that support this area
        if primary_source == Source.AEMO and not fallbacks:
            # Find all other sources that support this area
            for source, regions in SOURCE_REGION_SUPPORT.items():
                if source != Source.AEMO and area in regions:
                    fallbacks.append(source)

            # Sort by reliability
            fallbacks.sort(key=lambda s: SOURCE_RELIABILITY.get(s, 0), reverse=True)

            if fallbacks:
                _LOGGER.debug(f"Dynamically determined fallback sources for AEMO area {area}: {fallbacks}")
            else:
                _LOGGER.debug(f"No fallback sources available for AEMO area {area}")

        # Filter to only include sources that support this area
        return [s for s in fallbacks if area in SOURCE_REGION_SUPPORT.get(s, set())]

# Global registry
registry = ApiRegistry()

def register_apis():
    """Register all available API handlers."""
    # Register all APIs
    registry.register(Source.NORDPOOL, nordpool)
    registry.register(Source.ENERGI_DATA_SERVICE, energi_data)
    registry.register(Source.ENTSOE, entsoe)
    registry.register(Source.EPEX, epex)
    registry.register(Source.OMIE, omie)
    registry.register(Source.AEMO, aemo)
    registry.register(Source.STROMLIGNING, stromligning)
    registry.register(Source.COMED, comed)

# Register APIs on module import
register_apis()

async def fetch_day_ahead_prices(
    source_type: str, config: dict, area: str, currency: str,
    reference_time=None, hass=None, session=None
):  # pylint: disable=too-many-arguments
    """Fetch prices from a specific API."""
    return await registry.fetch_prices(source_type, config, area, currency, reference_time, hass, session)

def get_sources_for_region(region: str) -> List[str]:
    """Get sources supporting a region in priority order."""
    return registry.get_sources_for_region(region)

async def create_apis_for_region(
    region: str, config: dict, source_priority: Optional[List[str]] = None,
    session=None
) -> List[Dict[str, Any]]:
    """Create API instances for all sources supporting a region."""
    currency = config.get("currency", "EUR")
    return await registry.create_apis_for_region(
        region, config, currency, None, None, source_priority, session
    )

async def create_api(
    source_type: str, config: dict, area: str = None, currency: str = None,
    reference_time=None, hass=None, session=None
):  # pylint: disable=too-many-arguments
    """Create an API instance for a specific source type."""
    # Get the API handler for this source
    api_module = registry._apis.get(source_type)
    if not api_module:
        _LOGGER.error("Unknown source type: %s", source_type)
        return None

    # For class-based APIs (like EntsoEAPI)
    api_class_name = source_type.title().replace("_", "") + "API"
    if hasattr(api_module, api_class_name):
        api_class = getattr(api_module, api_class_name)
        return api_class(config)

    # For function-based APIs, return the module
    return api_module

def get_fallback_chain(primary_source: str, area: str) -> List[str]:
    """Get list of fallback sources for a primary source."""
    return registry.get_fallback_chain(primary_source, area)

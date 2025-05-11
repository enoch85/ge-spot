"""API module for the GE-Spot integration."""
import logging
from typing import List, Dict, Any, Optional

from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)

def get_sources_for_region(region: str) -> List[str]:
    """Get available sources for a region."""
    from ..const.areas import get_available_sources
    return get_available_sources(region)

def create_api(source_type: str, config: Optional[Dict[str, Any]] = None, session=None):
    """Create an API instance for the specified source type.

    Args:
        source_type: Source type identifier
        config: Optional configuration dictionary
        session: Optional session for API requests

    Returns:
        API instance for the specified source type
    """
    if source_type == Source.ENTSOE:
        from .entsoe import EntsoeAPI
        return EntsoeAPI(config, session)
    elif source_type == Source.NORDPOOL:
        from .nordpool import NordpoolAPI
        return NordpoolAPI(config, session)
    elif source_type == Source.ENERGI_DATA_SERVICE:
        from .energi_data import EnergiDataAPI
        return EnergiDataAPI(config, session)
    elif source_type == Source.AEMO:
        from .aemo import AemoAPI
        return AemoAPI(config, session)
    elif source_type == Source.EPEX:
        from .epex import EpexAPI
        return EpexAPI(config, session)
    elif source_type == Source.OMIE:
        from .omie import OmieAPI
        return OmieAPI(config, session)
    elif source_type == Source.STROMLIGNING:
        from .stromligning import StromligningAPI
        return StromligningAPI(config, session)
    elif source_type == Source.COMED:
        from .comed import ComedAPI
        return ComedAPI(config, session)
    else:
        raise ValueError(f"Unknown source type: {source_type}")

from .entsoe import EntsoeAdapter
from .epex import EpexAdapter # Standard EPEX SPOT API
from .nordpool import NordpoolAdapter
from .omie import OmieAdapter
from .stromligning import StromligningAdapter

# New Adapters from ha_epex_spot integration
from .awattar_adapter import AwattarAdapter
from .epex_spot_web_adapter import EpexSpotWebAdapter # EPEX Spot Web Scraper
from .energy_forecast_adapter import EnergyForecastAdapter
from .smard_adapter import SmardAdapter
from .tibber_adapter import TibberAdapter
from .smart_energy_adapter import SmartEnergyAdapter


# The @register_adapter decorator in each adapter file handles adding
# them to the registry. No explicit SOURCE_MAP update needed here if
# the dynamic registration mechanism is fully in place.

# Ensure all modules are imported so decorators run.

"""Price parsers for different API sources."""
from .nordpool_parser import NordpoolPriceParser
from .entsoe_parser import EntsoePriceParser
from .aemo_parser import AemoParser
from .energi_data_parser import EnergiDataParser
from .epex_parser import EpexParser
from .omie_parser import OmieParser
from .comed_parser import ComedParser
from .stromligning_parser import StromligningParser

from ...const.sources import Source

def get_parser_for_source(source_type: str, timezone_service=None):
    """Get the appropriate parser for the specified source.
    
    Args:
        source_type: Source type identifier
        timezone_service: Optional timezone service
        
    Returns:
        Parser instance for the source
    """
    parsers = {
        Source.NORDPOOL: NordpoolPriceParser,
        Source.ENTSOE: EntsoePriceParser,
        Source.AEMO: AemoParser,
        Source.ENERGI_DATA_SERVICE: EnergiDataParser,
        Source.EPEX: EpexParser,
        Source.OMIE: OmieParser,
        Source.COMED: ComedParser,
        Source.STROMLIGNING: StromligningParser
    }
    
    if source_type in parsers:
        parser_class = parsers[source_type]
        return parser_class(timezone_service)
    
    # Fallback to a generic parser
    from ..base.price_parser import BasePriceParser
    return BasePriceParser(source_type, timezone_service)

__all__ = [
    "NordpoolPriceParser",
    "EntsoePriceParser",
    "AemoParser", 
    "EnergiDataParser",
    "EpexParser",
    "OmieParser",
    "ComedParser",
    "StromligningParser",
    "get_parser_for_source"
]

"""Price parsers for different API sources."""

from .nordpool_parser import NordpoolParser
from .entsoe_parser import EntsoeParser
from .aemo_parser import AemoParser
from .energi_data_parser import EnergiDataParser
from .energy_charts_parser import EnergyChartsParser
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
        Source.NORDPOOL: NordpoolParser,
        Source.ENTSOE: EntsoeParser,
        Source.AEMO: AemoParser,
        Source.ENERGI_DATA_SERVICE: EnergiDataParser,
        Source.ENERGY_CHARTS: EnergyChartsParser,
        Source.OMIE: OmieParser,
        Source.COMED: ComedParser,
        Source.STROMLIGNING: StromligningParser,
    }

    if source_type in parsers:
        parser_class = parsers[source_type]
        return parser_class(timezone_service=timezone_service)

    # No fallback - unknown sources should raise an error
    raise ValueError(f"No parser available for source: {source_type}")


__all__ = [
    "NordpoolParser",
    "EntsoeParser",
    "AemoParser",
    "EnergiDataParser",
    "EnergyChartsParser",
    "OmieParser",
    "ComedParser",
    "StromligningParser",
    "get_parser_for_source",
]

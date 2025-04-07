"""Energy price sources for GE-Spot integration."""

# Available price sources
class Source:
    """API sources."""
    ENERGI_DATA_SERVICE = "energi_data_service"
    NORDPOOL = "nordpool"
    ENTSO_E = "entsoe"
    EPEX = "epex"
    OMIE = "omie"
    AEMO = "aemo"
    STROMLIGNING = "stromligning"

    ALL = [NORDPOOL, ENERGI_DATA_SERVICE, ENTSO_E, EPEX, OMIE, AEMO, STROMLIGNING]


# For backward compatibility - direct constants
SOURCE_ENERGI_DATA_SERVICE = Source.ENERGI_DATA_SERVICE
SOURCE_NORDPOOL = Source.NORDPOOL
SOURCE_ENTSO_E = Source.ENTSO_E
SOURCE_EPEX = Source.EPEX
SOURCE_OMIE = Source.OMIE
SOURCE_AEMO = Source.AEMO
SOURCE_STROMLIGNING = Source.STROMLIGNING

# List of all sources for backward compatibility
SOURCES = Source.ALL

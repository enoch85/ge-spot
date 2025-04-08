"""Energy price sources for GE-Spot integration."""

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
    
    # Source reliability ratings (higher is better)
    RELIABILITY = {
        NORDPOOL: 10,  # Most reliable
        ENERGI_DATA_SERVICE: 8,
        ENTSO_E: 7,
        EPEX: 7,
        OMIE: 6,
        AEMO: 6,
        STROMLIGNING: 8,  # Similar reliability to Energi Data Service
    }

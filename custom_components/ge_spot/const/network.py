"""Network-related constants for GE-Spot integration."""

class Network:
    """Network-related constants."""
    class Defaults:
        """Default network parameters."""
        TIMEOUT = 30
        RETRY_COUNT = 3
        RETRY_BASE_DELAY = 2.0
        CACHE_TTL = 21600  # 6 hours in seconds
        USER_AGENT = "HomeAssistantGESpot/1.0"
        
        # Rate limiting constants
        MIN_UPDATE_INTERVAL_MINUTES = 15  # Minimum time between fetches
        STANDARD_UPDATE_INTERVAL_MINUTES = 60  # Standard interval
        
        # Special time windows for updates
        SPECIAL_HOUR_WINDOWS = [
            (0, 1),   # 00:00-01:00 - For today's new prices
            (13, 14)  # 13:00-14:00 - For tomorrow's prices
        ]

    class URLs:
        """Base URLs for various APIs."""
        NORDPOOL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
        ENTSOE = "https://web-api.tp.entsoe.eu/api"
        STROMLIGNING = "https://stromligning.dk/api/prices"
        AEMO = "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY"
        ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
        OMIE_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"


class ContentType:
    """Content type constants."""
    JSON = "application/json"
    XML = "application/xml;charset=UTF-8"
    TEXT = "text/plain"

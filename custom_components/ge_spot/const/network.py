"""Network-related constants for GE-Spot integration."""

class NetworkDefaults:
    """Default network parameters."""
    TIMEOUT = 30
    RETRY_COUNT = 3
    RETRY_BASE_DELAY = 2.0
    CACHE_TTL = 86400  # 24 hours in seconds
    USER_AGENT = "HomeAssistantGESpot/1.0"

class URLs:
    """Base URLs for various APIs."""
    NORDPOOL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
    ENTSOE = "https://web-api.tp.entsoe.eu/api"
    STROMLIGNING = "https://stromligning.dk/api/prices"
    AEMO = "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY"
    ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

class ContentType:
    """Content type constants."""
    JSON = "application/json"
    XML = "application/xml;charset=UTF-8"
    TEXT = "text/plain"

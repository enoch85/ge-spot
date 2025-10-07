"""Network-related constants for GE-Spot integration."""

class Network:
    """Network-related constants."""
    class Defaults:
        """Default network parameters."""
        TIMEOUT = 30
        PARALLEL_FETCH_TIMEOUT = 30  # Timeout for parallel fetches
        RETRY_COUNT = 3
        RETRY_BASE_DELAY = 2.0
        CACHE_TTL = 21600  # 6 hours in seconds
        USER_AGENT = "HomeAssistantGESpot/1.0"

        # Rate limiting constants
        MIN_UPDATE_INTERVAL_MINUTES = 15  # Minimum time between fetches
        STANDARD_UPDATE_INTERVAL_MINUTES = 30  # Standard interval
        MISSING_HOURS_RETRY_INTERVAL_MINUTES = 5  # Minimum time between attempts to fill missing hours

        # Special time windows for updates
        SPECIAL_HOUR_WINDOWS = [
            (0, 1),   # 00:00-01:00 - For today's new prices
            (13, 15), # 13:00-15:00 - For tomorrow's data (most EU markets publish around 13:00-14:00 CET)
        ]
        
        # Data validity settings (in intervals, assuming 15-min intervals = 96/day)
        DATA_SAFETY_BUFFER_INTERVALS = 8  # Fetch when we have less than 8 intervals remaining (~2 hours)
        REQUIRED_TOMORROW_INTERVALS = 76  # Require at least 76 intervals (~80% of 96) to consider tomorrow data "complete"

    class URLs:
        """Base URLs for various APIs."""
        NORDPOOL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
        ENTSOE = "https://web-api.tp.entsoe.eu/api"
        STROMLIGNING = "https://stromligning.dk/api/prices"
        ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
        OMIE_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"
        ENERGY_CHARTS = "https://api.energy-charts.info"


class ContentType:
    """Content type constants."""
    JSON = "application/json"
    XML = "application/xml;charset=UTF-8"
    TEXT = "text/plain"


class NetworkErrorType:
    """Network error type constants for error classification."""
    CONNECTIVITY = "connectivity"  # Network connectivity issues
    RATE_LIMIT = "rate_limit"      # Rate limiting or throttling
    AUTHENTICATION = "authentication"  # Authentication or authorization issues
    SERVER = "server"              # Server-side errors
    DATA_FORMAT = "data_format"    # Data parsing or format issues
    TIMEOUT = "timeout"            # Request timeout
    DNS = "dns"                    # DNS resolution issues
    SSL = "ssl"                    # SSL/TLS issues
    UNKNOWN = "unknown"            # Unclassified errors


class RetryStrategy:
    """Retry strategy constants."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # Exponential backoff with jitter
    LINEAR_BACKOFF = "linear_backoff"            # Linear backoff
    CONSTANT_DELAY = "constant_delay"            # Constant delay between retries
    FIBONACCI_BACKOFF = "fibonacci_backoff"      # Fibonacci sequence backoff

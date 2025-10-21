"""Network-related constants for GE-Spot integration."""


class Network:
    """Network-related constants."""

    class Defaults:
        """Default network parameters."""

        # Exponential backoff configuration for source retry
        # Timeout progression: 2s → 6s → 18s (factor of 3)
        # Total max time per source: 2s + 6s + 18s = 26 seconds
        RETRY_BASE_TIMEOUT = 2  # Initial timeout: 2 seconds
        RETRY_TIMEOUT_MULTIPLIER = 3  # Each retry: 3x previous (2s → 6s → 18s)
        RETRY_COUNT = 3  # Total attempts per source

        # HTTP layer timeout (for individual network requests)
        # This is a safety net - FallbackManager controls the actual timeout strategy
        HTTP_TIMEOUT = 30  # seconds - basic HTTP request timeout

        CACHE_TTL = 21600  # 6 hours in seconds
        USER_AGENT = "HomeAssistantGESpot/1.0"

        # Rate limiting constants
        MIN_UPDATE_INTERVAL_MINUTES = 15  # Minimum time between fetches (normal hours)
        SPECIAL_WINDOW_MIN_INTERVAL_MINUTES = (
            5  # Minimum time between fetches during special windows (more API-friendly)
        )
        STANDARD_UPDATE_INTERVAL_MINUTES = 30  # Standard interval
        MISSING_HOURS_RETRY_INTERVAL_MINUTES = (
            5  # Minimum time between attempts to fill missing hours
        )
        GRACE_PERIOD_MINUTES = 5  # Grace period after reload/startup for lenient validation

        # Time conversion constants
        SECONDS_PER_MINUTE = 60  # Seconds in a minute (for time calculations)

        # Special time windows for updates
        # During these windows, rate limiting is more lenient (1 min vs 15 min) to catch new data quickly
        SPECIAL_HOUR_WINDOWS = [
            (0, 1),  # 00:00-01:00 - For today's new prices
            (
                13,
                15,
            ),  # 13:00-15:00 - For tomorrow's data (most EU markets publish around 13:00-14:00 CET)
        ]

        # Data validity settings (in intervals, assuming 15-min intervals = 96/day)
        DATA_SAFETY_BUFFER_INTERVALS = (
            8  # Fetch when we have less than 8 intervals remaining (~2 hours)
        )
        REQUIRED_TOMORROW_INTERVALS = (
            76  # Require at least 76 intervals (~80% of 96) to consider tomorrow data "complete"
        )

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
    RATE_LIMIT = "rate_limit"  # Rate limiting or throttling
    AUTHENTICATION = "authentication"  # Authentication or authorization issues
    SERVER = "server"  # Server-side errors
    DATA_FORMAT = "data_format"  # Data parsing or format issues
    TIMEOUT = "timeout"  # Request timeout
    DNS = "dns"  # DNS resolution issues
    SSL = "ssl"  # SSL/TLS issues
    UNKNOWN = "unknown"  # Unclassified errors


class RetryStrategy:
    """Retry strategy constants."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"  # Exponential backoff with jitter
    LINEAR_BACKOFF = "linear_backoff"  # Linear backoff
    CONSTANT_DELAY = "constant_delay"  # Constant delay between retries
    FIBONACCI_BACKOFF = "fibonacci_backoff"  # Fibonacci sequence backoff

"""Default values for GE-Spot integration."""
from .display import DisplayUnit
from .time import TimezoneReference

class Defaults:
    """Default configuration values."""
    NAME = "Electricity Price"
    VAT = 0.0
    VAT_RATE = 0  # Default VAT rate in percentage
    INCLUDE_VAT = False  # Whether to include VAT by default
    UPDATE_INTERVAL = 30  # minutes
    # Display & Formatting
    DISPLAY_UNIT = DisplayUnit.DECIMAL
    PRECISION = 4
    CURRENCY_SUBUNIT = "cents" # Added default for subunit check

    # Cache Settings
    CACHE_MAX_ENTRIES = 100
    CACHE_TTL = 3600 * 6 # 6 hours default TTL
    PERSIST_CACHE = False # Added default for cache persistence
    CACHE_DIR = "cache" # Added default cache directory

    # API & Network
    # Cache defaults
    CACHE_TTL = 60  # minutes
    CACHE_MAX_DAYS = 3  # days
    CACHE_MAX_ENTRIES = 10  # entries per area
    CACHE_COMPRESSION_THRESHOLD = 10240  # bytes (10KB)
    CACHE_CLEANUP_THRESHOLD = 100  # stores before auto cleanup
    CACHE_ADVANCED = True  # use advanced cache by default

    # Timezone defaults
    TIMEZONE_REFERENCE = TimezoneReference.DEFAULT

    # Error handling defaults
    ERROR_RETRY_COUNT = 3  # retries
    ERROR_RETRY_DELAY = 5  # seconds
    ERROR_BACKOFF_FACTOR = 2  # exponential backoff factor

    # Parallel fetching defaults
    PARALLEL_FETCH = True  # fetch in parallel by default
    PARALLEL_FETCH_TIMEOUT = 30  # seconds
    PARALLEL_FETCH_MAX_WORKERS = 5  # maximum number of workers

    # Data validation defaults
    VALIDATE_RESPONSES = True  # validate API responses
    VALIDATE_SCHEMA = True  # validate against schema
    VALIDATE_PRICE_RANGE = True  # validate price ranges
    PRICE_MIN = -1000  # minimum valid price (negative prices are possible)
    PRICE_MAX = 10000  # maximum valid price

    # Tomorrow data search defaults
    TOMORROW_DATA_INITIAL_RETRY_MINUTES = 15  # first retry after special window
    TOMORROW_DATA_MAX_RETRIES = 10  # maximum number of retries
    TOMORROW_DATA_BACKOFF_FACTOR = 1.5  # exponential backoff factor

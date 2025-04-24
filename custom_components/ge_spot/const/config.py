"""Configuration constants for GE-Spot integration."""

class Config:
    """Configuration constants."""
    SOURCE = "source"
    AREA = "area"
    VAT = "vat"
    INCLUDE_VAT = "include_vat"  # Whether to include VAT in price calculations
    UPDATE_INTERVAL = "update_interval"
    DISPLAY_UNIT = "display_unit"
    CURRENCY = "currency"
    PRECISION = "precision"
    API_KEY = "api_key"
    PRICE_IN_CENTS = "price_in_cents"

    # Cache configuration
    CACHE_TTL = "cache_ttl"  # Time to live in seconds
    CACHE_MAX_DAYS = "cache_max_days"  # Maximum number of days to keep in cache
    CACHE_MAX_ENTRIES = "cache_max_entries"  # Maximum number of entries per area
    CACHE_COMPRESSION_THRESHOLD = "cache_compression_threshold"  # Size threshold for compression
    CACHE_CLEANUP_THRESHOLD = "cache_cleanup_threshold"  # Number of stores before auto cleanup
    CACHE_ADVANCED = "cache_advanced"  # Whether to use advanced cache

    # API configuration
    SOURCE_PRIORITY = "source_priority"  # Priority order for data sources
    ORIGINAL_AREA = "original_area"  # Original area code before mapping
    TIMEZONE_REFERENCE = "timezone_reference"  # Timezone reference for area

    # Error handling configuration
    ERROR_RETRY_COUNT = "error_retry_count"  # Number of retries on error
    ERROR_RETRY_DELAY = "error_retry_delay"  # Delay between retries in seconds
    ERROR_BACKOFF_FACTOR = "error_backoff_factor"  # Exponential backoff factor

    # Parallel fetching configuration
    PARALLEL_FETCH = "parallel_fetch"  # Whether to fetch in parallel
    PARALLEL_FETCH_TIMEOUT = "parallel_fetch_timeout"  # Timeout for parallel fetching
    PARALLEL_FETCH_MAX_WORKERS = "parallel_fetch_max_workers"  # Maximum number of workers

    # Data validation configuration
    VALIDATE_RESPONSES = "validate_responses"  # Whether to validate API responses
    VALIDATE_SCHEMA = "validate_schema"  # Whether to validate against schema
    VALIDATE_PRICE_RANGE = "validate_price_range"  # Whether to validate price ranges
    PRICE_MIN = "price_min"  # Minimum valid price
    PRICE_MAX = "price_max"  # Maximum valid price

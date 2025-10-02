"""Configuration constants for GE-Spot integration."""

class Config:
    """Configuration keys used in the integration."""
    SOURCE = "source"
    AREA = "area"
    VAT = "vat"
    INCLUDE_VAT = "include_vat"  # Whether to include VAT in price calculations
    UPDATE_INTERVAL = "update_interval"
    DISPLAY_UNIT = "display_unit"
    CURRENCY = "currency"
    PRECISION = "precision"

    # Cache Settings
    CACHE_MAX_ENTRIES = "cache_max_entries"
    CACHE_TTL = "cache_ttl"
    PERSIST_CACHE = "persist_cache"
    CACHE_DIR = "cache_dir" # Added cache directory config key

    # API & Network
    # API Keys (Sensitive - Handled separately)
    API_KEY = "api_key"
    PRICE_IN_CENTS = "price_in_cents"

    # Stromligning specific
    CONF_STROMLIGNING_SUPPLIER = "stromligning_supplier"

    # API configuration
    SOURCE_PRIORITY = "source_priority"  # Priority order for data sources
    FALLBACK_SOURCES = "fallback_sources" # Added fallback sources config key
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

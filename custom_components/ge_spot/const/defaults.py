"""Default values for GE-Spot integration."""

from .display import DisplayUnit
from .time import TimezoneReference


class Defaults:
    """Default configuration values."""

    NAME = "Electricity Price"
    VAT = 0.0  # Default VAT rate as decimal (0.25 = 25%)
    INCLUDE_VAT = False  # Whether to include VAT by default
    IMPORT_MULTIPLIER = 1.0  # Default multiplier for import prices (1.0 = no scaling)
    ADDITIONAL_TARIFF = 0.0  # Default additional tariff (transfer fees, etc.) per kWh
    ENERGY_TAX = 0.0  # Default energy tax per kWh (applied before VAT)
    UPDATE_INTERVAL = 15  # Update every 15 minutes to match interval granularity
    # Display & Formatting
    DISPLAY_UNIT = DisplayUnit.DECIMAL
    PRECISION = 4
    CURRENCY_SUBUNIT = "cents"  # Added default for subunit check

    # Cache Settings
    CACHE_TTL = (
        60 * 24 * 3
    )  # minutes (3 days = 4320 minutes) - Electricity prices valid for 24-72 hours
    CACHE_MAX_ENTRIES = (
        3500  # Max cache entries (3 days × 24h × 4 intervals × ~12 areas = ~3500)
    )
    # Disk persistence disabled by default to avoid blocking I/O warnings in HA event loop
    # Cache remains in-memory only (cleared on reload). Can be enabled via config if needed.
    # See: https://developers.home-assistant.io/docs/asyncio_blocking_operations/#open
    PERSIST_CACHE = False
    CACHE_DIR = "cache"  # Cache directory for persistent storage (if enabled)

    # API & Network

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

    # Export/Production price defaults
    # Export prices use formula: (spot_price × multiplier + offset) × (1 + export_vat)
    # Default multiplier of 1.0 means export price equals spot price before offset/VAT
    EXPORT_ENABLED = False  # Export sensors disabled by default
    EXPORT_MULTIPLIER = 1.0  # Default multiplier (1.0 = no scaling)
    EXPORT_OFFSET = 0.0  # Default offset (0.0 = no offset)
    EXPORT_VAT = 0.0  # Default export VAT (0.0 = no VAT, common for feed-in)

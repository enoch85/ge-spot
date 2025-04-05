"""Default values for GE-Spot integration."""

# Default configurations
class Defaults:
    """Default values."""
    NAME = "Electricity Price"
    VAT = 0.0
    UPDATE_INTERVAL = 60  # minutes
    DISPLAY_UNIT = "decimal"  # default is decimal format (e.g., 0.15 EUR/kWh)
    PRECISION = 3
    CACHE_TTL = 60  # minutes


# For backward compatibility - direct constants
DEFAULT_NAME = Defaults.NAME
DEFAULT_VAT = Defaults.VAT
DEFAULT_UPDATE_INTERVAL = Defaults.UPDATE_INTERVAL
DEFAULT_DISPLAY_UNIT = Defaults.DISPLAY_UNIT
DEFAULT_PRECISION = Defaults.PRECISION
DEFAULT_CACHE_TTL = Defaults.CACHE_TTL

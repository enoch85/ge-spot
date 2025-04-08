"""Default values for GE-Spot integration."""
from .display import DisplayUnit

class Defaults:
    """Default values."""
    NAME = "Electricity Price"
    VAT = 0.0
    UPDATE_INTERVAL = 60  # minutes
    DISPLAY_UNIT = DisplayUnit.DECIMAL
    PRECISION = 3
    CACHE_TTL = 60  # minutes

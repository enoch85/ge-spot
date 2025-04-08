"""Constants for the GE-Spot integration."""

# Domain - keep as direct constants since these are singleton values
DOMAIN = "ge_spot"
CONFIG_VERSION = 1

# Import all constants as classes from their submodules
from .config import Config
from .defaults import Defaults
from .sources import Source
from .areas import (
    # Keep non-class mappings as-is
    AREA_TIMEZONES,
    ENTSOE_AREA_MAPPING,
    ENTSOE_AREAS,
    NORDPOOL_AREAS,
    ENERGI_DATA_AREAS,
    EPEX_AREAS,
    OMIE_AREAS,
    AEMO_AREAS,
    STROMLIGNING_AREAS,
    DEFAULT_AREAS,
    NORDPOOL_DELIVERY_AREA_MAPPING
)
from .currencies import (
    Currency,
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_MULTIPLIER,
    CURRENCY_SUBUNIT_NAMES,
    ENERGY_UNIT_CONVERSION,
)
from .precision import (
    # For now keep these as direct constants
    PRICE_PRECISION,
    PRICE_PRECISION_HIGH,
    PRICE_PRECISION_LOW,
    PRICE_FORMAT_DEFAULT,
    PRICE_FORMAT_EURO,
    PRICE_FORMAT_PERCENT
)
from .display import (
    # For now keep these as direct constants
    DISPLAY_UNIT_DECIMAL, 
    DISPLAY_UNIT_CENTS,
    DISPLAY_UNITS,
    UPDATE_INTERVAL_OPTIONS
)
from .sensors import SensorType
from .attributes import Attributes
from .errors import ErrorMessages, TRANSLATIONS

# Keep CONFIG_ORIGINAL_AREA as is (not a class constant)
CONF_ORIGINAL_AREA = "original_area"

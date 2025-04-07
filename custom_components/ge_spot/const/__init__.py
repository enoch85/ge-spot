"""Constants for the GE-Spot integration."""

# Add a constant for storing original area
CONF_ORIGINAL_AREA = "original_area"

# Import all constants from their submodules
from .config import Config
from .defaults import Defaults
from .sources import Source
from .areas import (
    # Export Areas as an alias for the entire areas module
    Areas,
    # All specific area constants remain the same
    AREA_TIMEZONES,
    ENTSOE_AREA_MAPPING,
    ENTSOE_AREAS,
    NORDPOOL_AREAS,
    ENERGI_DATA_AREAS,
    EPEX_AREAS,
    OMIE_AREAS,
    AEMO_AREAS,
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
    PRICE_PRECISION,
    PRICE_PRECISION_HIGH,
    PRICE_PRECISION_LOW,
    PRICE_FORMAT_DEFAULT,
    PRICE_FORMAT_EURO,
    PRICE_FORMAT_PERCENT
)
from .display import (
    DISPLAY_UNIT_DECIMAL,
    DISPLAY_UNIT_CENTS,
    DISPLAY_UNITS,
    UPDATE_INTERVAL_OPTIONS
)
from .sensors import SensorType
from .attributes import Attributes
from .errors import ErrorMessages, TRANSLATIONS

# Domain
DOMAIN = "ge_spot"
CONFIG_VERSION = 1

# Re-export specific constants for direct access
CONF_AREA = Config.AREA
CONF_VAT = Config.VAT
CONF_UPDATE_INTERVAL = Config.UPDATE_INTERVAL
CONF_DISPLAY_UNIT = Config.DISPLAY_UNIT
CONF_CURRENCY = Config.CURRENCY
CONF_API_KEY = Config.API_KEY
CONF_SOURCE_PRIORITY = Config.SOURCE_PRIORITY

# More re-exports as needed
DEFAULT_VAT = Defaults.VAT
DEFAULT_UPDATE_INTERVAL = Defaults.UPDATE_INTERVAL
DEFAULT_DISPLAY_UNIT = Defaults.DISPLAY_UNIT

# Export sources for easy access
SOURCE_NORDPOOL = Source.NORDPOOL
SOURCE_ENERGI_DATA_SERVICE = Source.ENERGI_DATA_SERVICE
SOURCE_ENTSO_E = Source.ENTSO_E
SOURCE_EPEX = Source.EPEX
SOURCE_OMIE = Source.OMIE
SOURCE_AEMO = Source.AEMO

# Attributes for easy access
ATTR_DATA_SOURCE = Attributes.DATA_SOURCE
ATTR_FALLBACK_USED = Attributes.FALLBACK_USED
ATTR_RAW_API_DATA = Attributes.RAW_API_DATA
ATTR_RAW_VALUES = Attributes.RAW_VALUES
ATTR_FALLBACK_INFO = Attributes.FALLBACK_INFO
ATTR_USING_CACHED_DATA = Attributes.USING_CACHED_DATA
ATTR_ATTEMPTED_SOURCES = Attributes.ATTEMPTED_SOURCES
ATTR_PRIMARY_SOURCE = Attributes.PRIMARY_SOURCE
ATTR_ACTIVE_SOURCE = Attributes.ACTIVE_SOURCE
ATTR_RAW_VALUE = Attributes.RAW_VALUE
ATTR_CONVERSION_INFO = Attributes.CONVERSION_INFO
ATTR_CURRENCY = Attributes.CURRENCY
ATTR_AREA = Attributes.AREA
ATTR_VAT = Attributes.VAT
ATTR_TODAY = Attributes.TODAY
ATTR_TOMORROW = Attributes.TOMORROW
ATTR_TOMORROW_VALID = Attributes.TOMORROW_VALID
ATTR_RAW_TODAY = Attributes.RAW_TODAY
ATTR_RAW_TOMORROW = Attributes.RAW_TOMORROW
ATTR_CURRENT_PRICE = Attributes.CURRENT_PRICE
ATTR_MIN = Attributes.MIN
ATTR_MAX = Attributes.MAX
ATTR_AVERAGE = Attributes.AVERAGE
ATTR_OFF_PEAK_1 = Attributes.OFF_PEAK_1
ATTR_OFF_PEAK_2 = Attributes.OFF_PEAK_2
ATTR_PEAK = Attributes.PEAK
ATTR_LAST_UPDATED = Attributes.LAST_UPDATED
ATTR_AVAILABLE_FALLBACKS = Attributes.AVAILABLE_FALLBACKS
ATTR_IS_USING_FALLBACK = Attributes.IS_USING_FALLBACK
ATTR_API_KEY_STATUS = Attributes.API_KEY_STATUS

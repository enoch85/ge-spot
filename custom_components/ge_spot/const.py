"""Constants for the GE-Spot integration."""

# Domain
DOMAIN = "ge_spot"

# Configuration constants
class Config:
    """Configuration constants."""
    SOURCE = "source"
    AREA = "area"
    VAT = "vat"
    UPDATE_INTERVAL = "update_interval"
    DISPLAY_UNIT = "display_unit"
    ENABLE_FALLBACK = "enable_fallback"
    CURRENCY = "currency"
    PRECISION = "precision"
    API_KEY = "api_key"
    PRICE_IN_CENTS = "price_in_cents"
    CACHE_TTL = "cache_ttl"
    SOURCE_PRIORITY = "source_priority"


# For backward compatibility - direct constants
CONF_SOURCE = Config.SOURCE
CONF_AREA = Config.AREA
CONF_VAT = Config.VAT
CONF_UPDATE_INTERVAL = Config.UPDATE_INTERVAL
CONF_DISPLAY_UNIT = Config.DISPLAY_UNIT
CONF_ENABLE_FALLBACK = Config.ENABLE_FALLBACK
CONF_CURRENCY = Config.CURRENCY
CONF_PRECISION = Config.PRECISION
CONF_API_KEY = Config.API_KEY
CONF_PRICE_IN_CENTS = Config.PRICE_IN_CENTS
CONF_CACHE_TTL = Config.CACHE_TTL
CONF_SOURCE_PRIORITY = Config.SOURCE_PRIORITY

# Default configurations
class Defaults:
    """Default values."""
    NAME = "Electricity Price"
    VAT = 0.0
    UPDATE_INTERVAL = 60  # minutes
    DISPLAY_UNIT = "decimal"  # default is decimal format (e.g., 0.15 EUR/kWh)
    ENABLE_FALLBACK = True  # Enable fallback to other markets by default
    PRECISION = 3
    CACHE_TTL = 60  # minutes


# For backward compatibility - direct constants
DEFAULT_NAME = Defaults.NAME
DEFAULT_VAT = Defaults.VAT
DEFAULT_UPDATE_INTERVAL = Defaults.UPDATE_INTERVAL
DEFAULT_DISPLAY_UNIT = Defaults.DISPLAY_UNIT
DEFAULT_ENABLE_FALLBACK = Defaults.ENABLE_FALLBACK
DEFAULT_PRECISION = Defaults.PRECISION
DEFAULT_CACHE_TTL = Defaults.CACHE_TTL

# Available price sources
class Source:
    """API sources."""
    ENERGI_DATA_SERVICE = "energi_data_service"
    NORDPOOL = "nordpool"
    ENTSO_E = "entsoe"
    EPEX = "epex"
    OMIE = "omie"
    AEMO = "aemo"

    ALL = [NORDPOOL, ENERGI_DATA_SERVICE, ENTSO_E, EPEX, OMIE, AEMO]


# For backward compatibility - direct constants
SOURCE_ENERGI_DATA_SERVICE = Source.ENERGI_DATA_SERVICE
SOURCE_NORDPOOL = Source.NORDPOOL
SOURCE_ENTSO_E = Source.ENTSO_E
SOURCE_EPEX = Source.EPEX
SOURCE_OMIE = Source.OMIE
SOURCE_AEMO = Source.AEMO

# List of all sources for backward compatibility
SOURCES = Source.ALL

# New attribute names
class Attributes:
    """Sensor attributes."""
    DATA_SOURCE = "data_source"  # Which API provided the data
    FALLBACK_USED = "fallback_used"  # Whether a fallback API was used
    RAW_API_DATA = "raw_api_data"  # Raw, unprocessed API response
    RAW_VALUES = "raw_values"  # Raw values before conversion
    FALLBACK_INFO = "fallback_info"  # Detailed fallback information
    USING_CACHED_DATA = "using_cached_data"  # Whether using cached data
    ATTEMPTED_SOURCES = "attempted_sources"  # All attempted API sources
    PRIMARY_SOURCE = "primary_source"  # Original primary source
    ACTIVE_SOURCE = "active_source"  # Source that succeeded
    RAW_VALUE = "raw_value"  # Raw value for a specific metric
    CONVERSION_INFO = "conversion_info"  # Information about value conversions
    CURRENCY = "currency"
    AREA = "area"
    VAT = "vat"
    TODAY = "today"
    TOMORROW = "tomorrow"
    TOMORROW_VALID = "tomorrow_valid"
    RAW_TODAY = "raw_today"
    RAW_TOMORROW = "raw_tomorrow"
    CURRENT_PRICE = "current_price"
    MIN = "min"
    MAX = "max"
    AVERAGE = "average"
    OFF_PEAK_1 = "off_peak_1"
    OFF_PEAK_2 = "off_peak_2"
    PEAK = "peak"
    LAST_UPDATED = "last_updated"
    AVAILABLE_FALLBACKS = "available_fallbacks"  # List of available fallback sources
    IS_USING_FALLBACK = "is_using_fallback"  # Whether currently using a fallback
    API_KEY_STATUS = "api_key_status"  # Status of API key (valid/invalid)


# For backward compatibility - direct constants
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

# Display unit options
DISPLAY_UNIT_DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
DISPLAY_UNIT_CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

DISPLAY_UNITS = {
    DISPLAY_UNIT_DECIMAL: "Decimal (e.g., 0.15 EUR/kWh)",
    DISPLAY_UNIT_CENTS: "Cents/Öre (e.g., 15 cents/kWh)",
}

# Update interval options with longer durations
UPDATE_INTERVAL_OPTIONS = [
    {"value": 60, "label": "1 hour"},
    {"value": 360, "label": "6 hours"},
    {"value": 720, "label": "12 hours"},
    {"value": 1440, "label": "24 hours"},
]

# Sensor types
class SensorType:
    """Sensor types."""
    CURRENT = "current_price"
    NEXT = "next_hour_price"
    DAY_AVG = "day_average_price"
    PEAK = "peak_price"
    OFF_PEAK = "off_peak_price"
    TOMORROW_AVG = "tomorrow_average_price"
    TOMORROW_PEAK = "tomorrow_peak_price"
    TOMORROW_OFF_PEAK = "tomorrow_off_peak_price"

    ALL = [
        CURRENT, NEXT, DAY_AVG, PEAK, OFF_PEAK,
        TOMORROW_AVG, TOMORROW_PEAK, TOMORROW_OFF_PEAK
    ]


# For backward compatibility - direct constants
SENSOR_TYPE_CURRENT = SensorType.CURRENT
SENSOR_TYPE_NEXT = SensorType.NEXT
SENSOR_TYPE_DAY_AVG = SensorType.DAY_AVG
SENSOR_TYPE_PEAK = SensorType.PEAK
SENSOR_TYPE_OFF_PEAK = SensorType.OFF_PEAK
SENSOR_TYPE_TOMORROW_AVG = SensorType.TOMORROW_AVG
SENSOR_TYPE_TOMORROW_PEAK = SensorType.TOMORROW_PEAK
SENSOR_TYPE_TOMORROW_OFF_PEAK = SensorType.TOMORROW_OFF_PEAK

# Region to Currency mapping
REGION_TO_CURRENCY = {
    # Nordics
    "SE1": "SEK",
    "SE2": "SEK",
    "SE3": "SEK",
    "SE4": "SEK",
    "DK1": "DKK",
    "DK2": "DKK",
    "FI": "EUR",
    "NO1": "NOK",
    "NO2": "NOK",
    "NO3": "NOK",
    "NO4": "NOK",
    "NO5": "NOK",
    # Baltics
    "EE": "EUR",
    "LV": "EUR",
    "LT": "EUR",
    # Central Europe
    "AT": "EUR",
    "BE": "EUR",
    "FR": "EUR",
    "DE-LU": "EUR",
    "NL": "EUR",
    # UK
    "GB": "GBP",
    # Australia
    "NSW1": "AUD",
    "QLD1": "AUD",
    "SA1": "AUD",
    "TAS1": "AUD",
    "VIC1": "AUD",
    # Additional mappings (Norwegian regions)
    "Oslo": "NOK",
    "Kr.sand": "NOK",
    "Bergen": "NOK",
    "Molde": "NOK",
    "Tr.heim": "NOK",
    "Tromsø": "NOK",
}

# Currency subunit multipliers
CURRENCY_SUBUNIT_MULTIPLIER = {
    "EUR": 100,  # Euro to cents
    "SEK": 100,  # Swedish krona to öre
    "NOK": 100,  # Norwegian krone to øre
    "DKK": 100,  # Danish krone to øre
    "GBP": 100,  # Pound to pence
    "AUD": 100,  # Australian dollar to cents
}

# Currency subunit names
CURRENCY_SUBUNIT_NAMES = {
    "EUR": "cents",
    "SEK": "öre",
    "NOK": "øre",
    "DKK": "øre",
    "GBP": "pence",
    "AUD": "cents",
}

# Nordpool delivery area mapping
NORDPOOL_DELIVERY_AREA_MAPPING = {
    "Oslo": "Oslo",
    "Kr.sand": "Kr.sand",
    "Bergen": "Bergen",
    "Molde": "Molde",
    "Tr.heim": "Tr.heim",
    "Tromsø": "Tromsø",
    "SE1": "SE1",
    "SE2": "SE2",
    "SE3": "SE3",
    "SE4": "SE4",
    "DK1": "DK1",
    "DK2": "DK2",
    "FI": "FI",
    "EE": "EE",
    "LV": "LV",
    "LT": "LT",
}

# Energy unit conversion
ENERGY_UNIT_CONVERSION = {
    "MWh": 1,
    "kWh": 1000,
    "Wh": 1000000,
}

# Nordpool areas
NORDPOOL_AREAS = {
    "Oslo": "Norway (Oslo)",
    "Kr.sand": "Norway (Kr.sand)",
    "Bergen": "Norway (Bergen)",
    "Molde": "Norway (Molde)",
    "Tr.heim": "Norway (Tr.heim)",
    "Tromsø": "Norway (Tromsø)",
    "SE1": "Sweden (SE1)",
    "SE2": "Sweden (SE2)",
    "SE3": "Sweden (SE3)",
    "SE4": "Sweden (SE4)",
    "DK1": "Denmark (DK1)",
    "DK2": "Denmark (DK2)",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
}

# Energi Data Service areas
ENERGI_DATA_AREAS = {
    "DK1": "Denmark (DK1)",
    "DK2": "Denmark (DK2)",
}

# ENTSO-E area mapping from our area codes to ENTSO-E area codes
ENTSOE_AREA_MAPPING = {
    # Nordic regions
    "SE1": "10Y1001A1001A44P",
    "SE2": "10Y1001A1001A45N",
    "SE3": "10Y1001A1001A46L",
    "SE4": "10Y1001A1001A47J",
    "DK1": "10YDK-1--------W",
    "DK2": "10YDK-2--------M",
    "NO1": "10YNO-1--------2",
    "NO2": "10YNO-2--------T",
    "NO3": "10YNO-3--------J",
    "NO4": "10YNO-4--------9",
    "NO5": "10Y1001A1001A48H",
    "FI": "10YFI-1--------U",
    "EE": "10Y1001A1001A39I",
    "LV": "10YLV-1001A00074",
    "LT": "10YLT-1001A0008Q",
    
    # Central Europe
    "DE": "10Y1001A1001A83F",
    "DE-LU": "10Y1001A1001A82H",
    "AT": "10YAT-APG------L",
    "BE": "10YBE----------2",
    "NL": "10YNL----------L",
    "FR": "10YFR-RTE------C",
    "LU": "10YLU-CEGEDEL-NQ",
    "GB": "10YGB----------A",
    "IE": "10YIE-1001A00010",
    "ES": "10YES-REE------0",
    "PT": "10YPT-REN------W",
    "CH": "10YCH-SWISSGRIDZ",
    "IT": "10YIT-GRTN-----B",
    "CZ": "10YCZ-CEPS-----N",
    "PL": "10YPL-AREA-----S",
    "SI": "10YSI-ELES-----O",
    "SK": "10YSK-SEPS-----K",
    "HU": "10YHU-MAVIR----U",
    "RO": "10YRO-TEL------P",
    "BG": "10YCA-BULGARIA-R",
    "GR": "10YGR-HTSO-----Y",
    "HR": "10YHR-HEP------M",
    "RS": "10YCS-SERBIATSOV"
}

# ENTSO-E areas
ENTSOE_AREAS = {
    # Nordic regions
    "SE1": "Sweden (SE1)",
    "SE2": "Sweden (SE2)",
    "SE3": "Sweden (SE3)",
    "SE4": "Sweden (SE4)",
    "DK1": "Denmark (DK1)",
    "DK2": "Denmark (DK2)",
    "NO1": "Norway (NO1)",
    "NO2": "Norway (NO2)",
    "NO3": "Norway (NO3)",
    "NO4": "Norway (NO4)",
    "NO5": "Norway (NO5)",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
    
    # Central Europe
    "DE": "Germany",
    "DE-LU": "Germany-Luxembourg",
    "AT": "Austria",
    "BE": "Belgium",
    "NL": "Netherlands",
    "FR": "France",
    "LU": "Luxembourg",
    "GB": "Great Britain",
    "IE": "Ireland",
    "ES": "Spain",
    "PT": "Portugal",
    "CH": "Switzerland",
    "IT": "Italy",
    "CZ": "Czech Republic",
    "PL": "Poland",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "HU": "Hungary",
    "RO": "Romania",
    "BG": "Bulgaria",
    "GR": "Greece",
    "HR": "Croatia",
    "RS": "Serbia",
    
    # These require ENTSO-E codes to be used directly
    "10YBA-JPCC-----D": "Bosnia Herzegovina",
    "10YCS-CG-TSO---S": "Montenegro",
    "10YMK-MEPSO----8": "North Macedonia",
    "10YAL-KESH-----5": "Albania",
    "10Y1001C--00003F": "Ukraine",
    "10YTR-TEIAS----W": "Turkey",
    "10YCY-1001A0003J": "Cyprus",
    "10Y1001A1001A93C": "Malta"
}

# EPEX areas
EPEX_AREAS = {
    "DE-LU": "Germany-Luxembourg",
    "FR": "France",
    "BE": "Belgium",
    "NL": "Netherlands",
    "AT": "Austria",
}

# OMIE areas
OMIE_AREAS = {
    "ES": "Spain",
    "PT": "Portugal",
}

# AEMO areas
AEMO_AREAS = {
    "NSW1": "New South Wales (NSW1)",
    "QLD1": "Queensland (QLD1)",
    "SA1": "South Australia (SA1)",
    "TAS1": "Tasmania (TAS1)",
    "VIC1": "Victoria (VIC1)",
}

# Area to timezone mapping - useful for multiple API handlers
AREA_TIMEZONES = {
    "DK1": "Europe/Copenhagen",
    "DK2": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "EE": "Europe/Tallinn",
    "LT": "Europe/Vilnius",
    "LV": "Europe/Riga",
    "NO1": "Europe/Oslo",
    "NO2": "Europe/Oslo",
    "NO3": "Europe/Oslo",
    "NO4": "Europe/Oslo",
    "NO5": "Europe/Oslo",
    "SE1": "Europe/Stockholm",
    "SE2": "Europe/Stockholm",
    "SE3": "Europe/Stockholm",
    "SE4": "Europe/Stockholm",
    "SYS": "Europe/Stockholm",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "AT": "Europe/Vienna",
    "DE-LU": "Europe/Berlin",
    "GER": "Europe/Berlin",
    "Oslo": "Europe/Oslo",
    "Kr.sand": "Europe/Oslo",
    "Bergen": "Europe/Oslo",
    "Molde": "Europe/Oslo",
    "Tr.heim": "Europe/Oslo",
    "Tromsø": "Europe/Oslo"
}

# Default areas for each source
DEFAULT_AREAS = {
    SOURCE_NORDPOOL: "SE4",
    SOURCE_ENERGI_DATA_SERVICE: "DK1",
    SOURCE_ENTSO_E: "10YSE-4--------9",  # SE4
    SOURCE_EPEX: "DE-LU",
    SOURCE_OMIE: "ES",
    SOURCE_AEMO: "NSW1",
}

# Error message constants
class ErrorMessages:
    """Error message constants."""
    INVALID_API_KEY = "invalid_api_key"
    API_KEY_REQUIRED = "api_key_required"
    API_CREATION_FAILED = "api_creation_failed"
    NO_SOURCES_FOR_REGION = "no_sources_for_region"
    ERROR_SOURCES_FOR_REGION = "error_sources_for_region"
    UNKNOWN = "unknown"

# Translation strings
TRANSLATIONS = {
    ErrorMessages.INVALID_API_KEY: "API key validation failed. Please check your key and try again.",
    ErrorMessages.API_KEY_REQUIRED: "API key is required for this source.",
    ErrorMessages.API_CREATION_FAILED: "Failed to create API instance. Please try again.",
    ErrorMessages.NO_SOURCES_FOR_REGION: "No data sources available for this region.",
    ErrorMessages.ERROR_SOURCES_FOR_REGION: "Error retrieving sources for region.",
    ErrorMessages.UNKNOWN: "An unexpected error occurred.",
}

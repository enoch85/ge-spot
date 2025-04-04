"""Attribute constants for GE-Spot integration."""

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

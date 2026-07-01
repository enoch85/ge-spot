"""Attribute constants for GE-Spot integration."""


class Attributes:
    """Sensor attributes."""

    DATA_SOURCE = "data_source"  # Which API provided the data
    FALLBACK_USED = "fallback_used"  # Whether a fallback API was used
    RAW_API_DATA = "raw_api_data"  # Raw, unprocessed API response
    RAW_VALUES = "raw_values"  # Raw values before conversion
    FALLBACK_INFO = "fallback_info"  # Detailed fallback information
    USING_CACHED_DATA = "using_cached_data"  # Whether using cached data
    ATTEMPTED_SOURCES = "attempted_sources"  # All attempted API sources (backend only)
    ACTIVE_SOURCE = "active_source"  # Source that succeeded
    VALIDATED_SOURCES = "validated_sources"  # Sources proven to work
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
    API_KEY_STATUS = "api_key_status"  # Status of API key (valid/invalid)

    # Exchange rate attributes
    EXCHANGE_RATE = "exchange_rate"
    EXCHANGE_RATE_FORMATTED = "exchange_rate_formatted"
    EXCHANGE_RATE_TIMESTAMP = "exchange_rate_timestamp"
    DATA_SOURCE_ATTRIBUTION = "data_source_attribution"  # Added for Stromligning

    # Consumption-weighted average ("your own average") attributes
    ENERGY_SOURCE = "energy_source"  # entity_id of the consumption sensor
    CONSUMED_ENERGY = "consumed_energy"  # kWh consumed this period
    ACCUMULATED_COST = "accumulated_cost"  # cost this period (in display unit)
    SIMPLE_AVERAGE = "simple_average"  # unweighted market avg over same window
    SAVINGS_VS_AVERAGE = (
        "savings_vs_average"  # simple_average - weighted (>0 = beating)
    )
    BEATING_AVERAGE = "beating_average"  # bool: weighted < simple_average
    PERIOD = "period"  # "daily" or "monthly"
    PERIOD_START = "period_start"  # key marking when accumulation started

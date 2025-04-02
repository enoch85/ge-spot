"""Constants for the GE-Spot integration."""

# Domain
DOMAIN = "ge_spot"

# Configuration constants
CONF_SOURCE = "source"
CONF_AREA = "area"
CONF_VAT = "vat"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DISPLAY_UNIT = "display_unit"
CONF_ENABLE_FALLBACK = "enable_fallback"
CONF_CURRENCY = "currency"
CONF_PRECISION = "precision"
CONF_API_KEY = "api_key"
CONF_PRICE_IN_CENTS = "price_in_cents"

# Default configurations
DEFAULT_NAME = "Electricity Price"
DEFAULT_VAT = 0.0
DEFAULT_UPDATE_INTERVAL = 60  # minutes
DEFAULT_DISPLAY_UNIT = "decimal"  # default is decimal format (e.g., 0.15 EUR/kWh)
DEFAULT_ENABLE_FALLBACK = True  # Enable fallback to other markets by default
DEFAULT_PRECISION = 3

# Available price sources
SOURCE_ENERGI_DATA_SERVICE = "energi_data_service"
SOURCE_NORDPOOL = "nordpool"
SOURCE_ENTSO_E = "entsoe"
SOURCE_EPEX = "epex"
SOURCE_OMIE = "omie"
SOURCE_AEMO = "aemo"

# List of all sources
SOURCES = [
    SOURCE_NORDPOOL,  # Reordered to put Nordpool first in the list
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
]

# Display unit options
DISPLAY_UNIT_DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
DISPLAY_UNIT_CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

DISPLAY_UNITS = {
    DISPLAY_UNIT_DECIMAL: "Decimal (e.g., 0.15 EUR/kWh)",
    DISPLAY_UNIT_CENTS: "Cents/Öre (e.g., 15 cents/kWh)",
}

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

# Energy unit conversion
ENERGY_UNIT_CONVERSION = {
    "MWh": 1,
    "kWh": 1000,
    "Wh": 1000000,
}

# Sensor types
SENSOR_TYPE_CURRENT = "current_price"
SENSOR_TYPE_NEXT = "next_hour_price"
SENSOR_TYPE_DAY_AVG = "day_average_price"
SENSOR_TYPE_PEAK = "peak_price"
SENSOR_TYPE_OFF_PEAK = "off_peak_price"
SENSOR_TYPE_TOMORROW_AVG = "tomorrow_average_price"
SENSOR_TYPE_TOMORROW_PEAK = "tomorrow_peak_price"
SENSOR_TYPE_TOMORROW_OFF_PEAK = "tomorrow_off_peak_price"

# Attribute names
ATTR_CURRENCY = "currency"
ATTR_AREA = "area" 
ATTR_VAT = "vat"
ATTR_TODAY = "today"
ATTR_TOMORROW = "tomorrow"
ATTR_TOMORROW_VALID = "tomorrow_valid"
ATTR_RAW_TODAY = "raw_today"
ATTR_RAW_TOMORROW = "raw_tomorrow"
ATTR_CURRENT_PRICE = "current_price"
ATTR_MIN = "min"
ATTR_MAX = "max"
ATTR_AVERAGE = "average"
ATTR_OFF_PEAK_1 = "off_peak_1"
ATTR_OFF_PEAK_2 = "off_peak_2"
ATTR_PEAK = "peak"
ATTR_LAST_UPDATED = "last_updated"

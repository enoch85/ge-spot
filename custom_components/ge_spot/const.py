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

# Nordpool areas
NORDPOOL_AREAS = {
    "Oslo": "Norway (Oslo)",
    "Kr.sand": "Norway (Kristiansand)",
    "Bergen": "Norway (Bergen)",
    "Molde": "Norway (Molde)",
    "Tr.heim": "Norway (Trondheim)",
    "Tromsø": "Norway (Tromsø)",
    "SE1": "Sweden (North)",
    "SE2": "Sweden (North-Central)",
    "SE3": "Sweden (South-Central)",
    "SE4": "Sweden (South)",
    "DK1": "Denmark (West)",
    "DK2": "Denmark (East)",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
}

# Energi Data Service areas
ENERGI_DATA_AREAS = {
    "DK1": "Denmark (West)",
    "DK2": "Denmark (East)",
}

# ENTSO-E areas
ENTSOE_AREAS = {
    "10YDK-1--------W": "Denmark (DK1)",
    "10YDK-2--------M": "Denmark (DK2)",
    "10YSE-1--------K": "Sweden (SE1)",
    "10YSE-2--------8": "Sweden (SE2)",
    "10YSE-3--------J": "Sweden (SE3)",
    "10YSE-4--------9": "Sweden (SE4)",
    "10YFI-1--------U": "Finland",
    "10YNO-1--------2": "Norway (NO1)",
    "10YNO-2--------T": "Norway (NO2)",
    "10YNO-3--------J": "Norway (NO3)",
    "10YNO-4--------9": "Norway (NO4)",
    "10Y1001A1001A83F": "Germany",
    "10YFR-RTE------C": "France",
    "10YBE----------2": "Belgium",
    "10YNL----------L": "Netherlands",
    "10YAT-APG------L": "Austria",
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
    "NSW1": "New South Wales",
    "QLD1": "Queensland",
    "SA1": "South Australia",
    "TAS1": "Tasmania",
    "VIC1": "Victoria",
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

# Configuration constants
DOMAIN = "ge_spot"
CONF_SOURCE = "source"
CONF_AREA = "area"
CONF_VAT = "vat"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DISPLAY_UNIT = "display_unit"
CONF_ENABLE_FALLBACK = "enable_fallback"

# Available price sources
SOURCE_ENERGI_DATA_SERVICE = "energi_data_service"
SOURCE_NORDPOOL = "nordpool"
SOURCE_ENTSO_E = "entso_e"
SOURCE_EPEX = "epex"
SOURCE_OMIE = "omie"
SOURCE_AEMO = "aemo"

SOURCES = [
    SOURCE_NORDPOOL,  # Reordered to put Nordpool first in the list
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
]

# Default configurations
DEFAULT_NAME = "Electricity Price"  # Changed from "Energy Price" to be more specific
DEFAULT_VAT = 0.0
DEFAULT_UPDATE_INTERVAL = 60  # minutes
DEFAULT_DISPLAY_UNIT = "decimal"  # default is decimal format (e.g., 0.15 EUR/kWh)
DEFAULT_ENABLE_FALLBACK = True  # Enable fallback to other markets by default

# Display unit options
DISPLAY_UNIT_DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
DISPLAY_UNIT_CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

DISPLAY_UNITS = {
    DISPLAY_UNIT_DECIMAL: "Decimal (e.g., 0.15 EUR/kWh)",
    DISPLAY_UNIT_CENTS: "Cents/Öre (e.g., 15 cents/kWh)",
}

# Source-specific constants
NORDPOOL_AREAS = {
    "Oslo": "Oslo (Norway)",
    "Kr.sand": "Kristiansand (Norway)",
    "Bergen": "Bergen (Norway)",
    "Molde": "Molde (Norway)",
    "Tr.heim": "Trondheim (Norway)",
    "Tromsø": "Tromsø (Norway)",
    "SE1": "Luleå (Sweden)",
    "SE2": "Sundsvall (Sweden)",
    "SE3": "Stockholm (Sweden)",
    "SE4": "Malmö (Sweden)",
    "DK1": "Western Denmark",
    "DK2": "Eastern Denmark",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
}

ENERGI_DATA_AREAS = {
    "DK1": "Western Denmark",
    "DK2": "Eastern Denmark",
}

ENTSOE_AREAS = {
    "10YDK-1--------W": "Denmark (DK1)",
    "10YDK-2--------M": "Denmark (DK2)",
    "10YFI-1--------U": "Finland",
    "10YNO-1--------2": "Norway (Oslo)",
    "10YNO-2--------T": "Norway (Kr.sand)",
    "10YNO-3--------J": "Norway (Bergen)",
    "10YNO-4--------9": "Norway (Tr.heim)",
    "10YSE-1--------K": "Sweden (SE1)",
    "10YSE-2--------8": "Sweden (SE2)",
    "10YSE-3--------J": "Sweden (SE3)",
    "10YSE-4--------9": "Sweden (SE4)",
    "10Y1001A1001A92E": "Great Britain",
    "10YCZ-CEPS-----N": "Czech Republic",
    "10YDE-RWENET---I": "Germany",
    "10YIT-GRTN-----B": "Italy",
    "10YPL-AREA-----S": "Poland",
    "10YES-REE------0": "Spain",
    "10YPT-REN------W": "Portugal",
    "10YFR-RTE------C": "France",
}

EPEX_AREAS = {
    "DE-LU": "Germany-Luxembourg",
    "FR": "France",
    "NL": "Netherlands",
    "BE": "Belgium",
    "AT": "Austria",
    "CH": "Switzerland",
    "GB": "Great Britain",
}

OMIE_AREAS = {
    "ES": "Spain",
    "PT": "Portugal",
}

AEMO_AREAS = {
    "NSW1": "New South Wales",
    "QLD1": "Queensland",
    "SA1": "South Australia",
    "TAS1": "Tasmania",
    "VIC1": "Victoria",
}

# Map similar regions across different sources for fallback functionality
REGION_FALLBACKS = {
    # Nordpool areas
    "SE1": {"entsoe": "10YSE-1--------K"},
    "SE2": {"entsoe": "10YSE-2--------8"},
    "SE3": {"entsoe": "10YSE-3--------J"},
    "SE4": {"entsoe": "10YSE-4--------9"},
    "DK1": {"energi_data_service": "DK1", "entsoe": "10YDK-1--------W"},
    "DK2": {"energi_data_service": "DK2", "entsoe": "10YDK-2--------M"},
    "FI": {"entsoe": "10YFI-1--------U"},
    "Oslo": {"entsoe": "10YNO-1--------2"},
    "Kr.sand": {"entsoe": "10YNO-2--------T"},
    "Bergen": {"entsoe": "10YNO-3--------J"},
    "Tr.heim": {"entsoe": "10YNO-4--------9"},
    
    # ENTSO-E areas (reverse mapping)
    "10YSE-1--------K": {"nordpool": "SE1"},
    "10YSE-2--------8": {"nordpool": "SE2"},
    "10YSE-3--------J": {"nordpool": "SE3"},
    "10YSE-4--------9": {"nordpool": "SE4"},
    "10YDK-1--------W": {"nordpool": "DK1", "energi_data_service": "DK1"},
    "10YDK-2--------M": {"nordpool": "DK2", "energi_data_service": "DK2"},
    "10YFI-1--------U": {"nordpool": "FI"},
    "10YNO-1--------2": {"nordpool": "Oslo"},
    "10YNO-2--------T": {"nordpool": "Kr.sand"},
    "10YNO-3--------J": {"nordpool": "Bergen"},
    "10YNO-4--------9": {"nordpool": "Tr.heim"},
    
    # Other mappings can be added as needed
}

CURRENCY_BY_SOURCE = {
    SOURCE_ENERGI_DATA_SERVICE: "DKK",
    SOURCE_NORDPOOL: {
        "DK1": "DKK",
        "DK2": "DKK",
        "SE1": "SEK",
        "SE2": "SEK",
        "SE3": "SEK",
        "SE4": "SEK",
        "Oslo": "NOK",
        "Kr.sand": "NOK",
        "Bergen": "NOK",
        "Molde": "NOK",
        "Tr.heim": "NOK",
        "Tromsø": "NOK",
        "FI": "EUR",
        "EE": "EUR",
        "LV": "EUR",
        "LT": "EUR",
    },
    SOURCE_ENTSO_E: "EUR",
    SOURCE_EPEX: "EUR",
    SOURCE_OMIE: "EUR",
    SOURCE_AEMO: "AUD",
}

# Currency subunit mapping (for cents/öre display)
CURRENCY_SUBUNITS = {
    "EUR": "cents",
    "DKK": "øre",
    "SEK": "öre",
    "NOK": "øre",
    "AUD": "cents",
    "GBP": "pence",
}

# Sensor types
SENSOR_TYPE_CURRENT = "current_price"
SENSOR_TYPE_NEXT = "next_hour_price"
SENSOR_TYPE_DAY_AVG = "day_average_price"
SENSOR_TYPE_PEAK = "peak_price"
SENSOR_TYPE_OFF_PEAK = "off_peak_price"

# New sensor types for tomorrow's prices
SENSOR_TYPE_TOMORROW_AVG = "tomorrow_average_price"
SENSOR_TYPE_TOMORROW_PEAK = "tomorrow_peak_price"
SENSOR_TYPE_TOMORROW_OFF_PEAK = "tomorrow_off_peak_price"

# Generic sensor names (for source-agnostic sensors)
GENERIC_SENSOR_NAMES = {
    SENSOR_TYPE_CURRENT: "Electricity Current Price",
    SENSOR_TYPE_NEXT: "Electricity Next Hour Price",
    SENSOR_TYPE_DAY_AVG: "Electricity Day Average Price",
    SENSOR_TYPE_PEAK: "Electricity Peak Price",
    SENSOR_TYPE_OFF_PEAK: "Electricity Off-Peak Price",
    SENSOR_TYPE_TOMORROW_AVG: "Electricity Tomorrow Average Price",
    SENSOR_TYPE_TOMORROW_PEAK: "Electricity Tomorrow Peak Price",
    SENSOR_TYPE_TOMORROW_OFF_PEAK: "Electricity Tomorrow Off-Peak Price",
}

# Fallback order for price sources (priority order)
FALLBACK_SOURCE_ORDER = [
    SOURCE_NORDPOOL,
    SOURCE_ENTSO_E,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
]

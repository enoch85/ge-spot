# Configuration constants
DOMAIN = "ge_spot"
CONF_SOURCE = "source"
CONF_AREA = "area"
CONF_VAT = "vat"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DISPLAY_UNIT = "display_unit"

# Available price sources
SOURCE_ENERGI_DATA_SERVICE = "energi_data_service"
SOURCE_NORDPOOL = "nordpool"
SOURCE_ENTSO_E = "entso_e"
SOURCE_EPEX = "epex"
SOURCE_OMIE = "omie"
SOURCE_AEMO = "aemo"

SOURCES = [
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_NORDPOOL,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
]

# Default configurations
DEFAULT_NAME = "Energy Price"
DEFAULT_VAT = 0.0
DEFAULT_UPDATE_INTERVAL = 60  # minutes
DEFAULT_DISPLAY_UNIT = "decimal"  # default is decimal format (e.g., 0.15 EUR/kWh)

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
SENSOR_TYPE_CURRENT = "current"
SENSOR_TYPE_NEXT = "next"
SENSOR_TYPE_DAY_AVG = "day_average"
SENSOR_TYPE_PEAK = "peak_price"
SENSOR_TYPE_OFF_PEAK = "off_peak_price"

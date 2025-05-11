"""Constants for the GE-Spot integration."""

# Domain and version - these stay as top-level constants as they're foundational identifiers
DOMAIN = "ge_spot"
CONFIG_VERSION = 1

# Import all constant classes
from .config import Config
from .defaults import Defaults
from .sources import (
    Source,
    SOURCE_NORDPOOL,
    SOURCE_ENTSOE,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_AEMO,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_STROMLIGNING,
    SOURCE_COMED,
    SOURCE_AMBER,
    SOURCE_AWATTAR,
    SOURCE_EPEX_SPOT_WEB,
    SOURCE_ENERGY_FORECAST,
    SOURCE_SMARD,
    SOURCE_TIBBER,
    SOURCE_SMART_ENERGY
)
from .areas import Area, AreaMapping, Timezone
from .currencies import Currency, CurrencyInfo, CURRENCY_EUR, CURRENCY_DKK, CURRENCY_NOK, CURRENCY_SEK, CURRENCY_GBP, CURRENCY_AUD, CURRENCY_USD
from .display import DisplayUnit, UpdateInterval
from .energy import EnergyUnit
from .network import Network, ContentType, NETWORK_TIMEOUT, NETWORK_RETRY_COUNT
from .time import TimeFormat, TimeInterval, PeriodType, DSTTransitionType, TimezoneConstants, TimezoneReference
from .sensors import SensorType
from .attributes import Attributes
from .errors import ErrorMessages, Errors
from .api import (EntsoE, Nordpool, Omie, Stromligning, ECB, SourceTimezone, API_RESPONSE_PRICE, API_RESPONSE_START_TIME)

__all__ = [
    # Top-level constants
    "DOMAIN",
    "CONFIG_VERSION",

    # Classes
    "Config",
    "Defaults",
    "Source",
    "SOURCE_NORDPOOL",
    "SOURCE_ENTSOE",
    "SOURCE_ENERGI_DATA_SERVICE",
    "SOURCE_AEMO",
    "SOURCE_EPEX",
    "SOURCE_OMIE",
    "SOURCE_STROMLIGNING",
    "SOURCE_COMED",
    "SOURCE_AMBER",
    "SOURCE_AWATTAR",
    "SOURCE_EPEX_SPOT_WEB",
    "SOURCE_ENERGY_FORECAST",
    "SOURCE_SMARD",
    "SOURCE_TIBBER",
    "SOURCE_SMART_ENERGY",
    "Area",
    "AreaMapping",
    "Timezone",
    "Currency",
    "CurrencyInfo",
    "CURRENCY_EUR",
    "CURRENCY_DKK",
    "CURRENCY_NOK",
    "CURRENCY_SEK",
    "CURRENCY_GBP",
    "CURRENCY_AUD",
    "CURRENCY_USD",
    "DisplayUnit",
    "UpdateInterval",
    "EnergyUnit",
    "Network",
    "ContentType",
    "NETWORK_TIMEOUT",
    "NETWORK_RETRY_COUNT",
    "TimeFormat",
    "TimeInterval",
    "PeriodType",
    "DSTTransitionType",
    "TimezoneConstants",
    "TimezoneReference",
    "SensorType",
    "Attributes",
    "ErrorMessages",
    "Errors",
    "EntsoE",
    "Nordpool",
    "Omie",
    "Stromligning",
    "ECB",
    "SourceTimezone",
    "API_RESPONSE_PRICE",
    "API_RESPONSE_START_TIME"
]

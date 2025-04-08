"""Constants for the GE-Spot integration."""

# Domain and version - these stay as top-level constants as they're foundational identifiers
DOMAIN = "ge_spot"
CONFIG_VERSION = 1

# Import all constant classes
from .config import Config
from .defaults import Defaults
from .sources import Source
from .areas import Area, AreaMapping, Timezone
from .currencies import Currency, CurrencyInfo
from .display import DisplayUnit, UpdateInterval
from .energy import EnergyUnit
from .network import Network, ContentType
from .time import TimeFormat, TimeInterval, PeriodType
from .sensors import SensorType
from .attributes import Attributes
from .errors import ErrorMessages
from .api import (EntsoE, Nordpool, Omie, Stromligning, ECB)

__all__ = [
    # Top-level constants
    "DOMAIN",
    "CONFIG_VERSION",
    
    # Classes
    "Config",
    "Defaults",
    "Source",
    "Area", 
    "AreaMapping",
    "Timezone",
    "Currency",
    "CurrencyInfo",
    "DisplayUnit",
    "UpdateInterval",
    "EnergyUnit",
    "Network",
    "ContentType",
    "TimeFormat",
    "TimeInterval", 
    "PeriodType",
    "SensorType",
    "Attributes",
    "ErrorMessages",
    "EntsoE",
    "Nordpool",
    "Omie",
    "Stromligning",
    "ECB"
]

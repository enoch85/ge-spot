"""Price handling functionality for electricity prices."""
from .adapter import ElectricityPriceAdapter
from .conversion import convert_energy_price, async_convert_energy_price, mwh_to_kwh
from .currency import (
    get_default_currency,
    convert_to_subunit,
    get_subunit_name,
    format_price,
)
from .energy import (
    convert_energy_unit,
    ENERGY_UNIT_CONVERSION
)
from .statistics import (
    get_statistics,
    find_extrema_with_timestamps,
    get_price_statistics
)
from .cache import PriceCache

__all__ = [
    # Adapter
    "ElectricityPriceAdapter",

    # Conversion functions
    "convert_energy_price",
    "async_convert_energy_price",
    "mwh_to_kwh",

    # Currency functions
    "get_default_currency",
    "convert_to_subunit",
    "get_subunit_name",
    "format_price",

    # Energy functions
    "convert_energy_unit",
    "ENERGY_UNIT_CONVERSION",

    # Statistics functions
    "get_statistics",
    "find_extrema_with_timestamps",
    "get_price_statistics",

    # Cache
    "PriceCache",
]

"""Energy unit conversion functionality."""
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

# Energy unit conversion factors
ENERGY_UNIT_CONVERSION = {
    "MWh": 1,
    "kWh": 1000,
    "Wh": 1000000,
}

def convert_energy_unit(price: Optional[float], from_unit: str, to_unit: str) -> Optional[float]:
    """Convert price between energy units.

    Args:
        price: The price value to convert
        from_unit: Source energy unit (e.g., "MWh")
        to_unit: Target energy unit (e.g., "kWh")

    Returns:
        Converted price value
    """
    if price is None:
        return None

    if from_unit == to_unit:
        return price

    if from_unit not in ENERGY_UNIT_CONVERSION or to_unit not in ENERGY_UNIT_CONVERSION:
        _LOGGER.error(f"Unsupported energy units: {from_unit} -> {to_unit}")
        return price

    # Get conversion factors
    from_factor = ENERGY_UNIT_CONVERSION[from_unit]
    to_factor = ENERGY_UNIT_CONVERSION[to_unit]

    # For price conversion, the formula is inverse of energy conversion
    # e.g., MWh to kWh: price per MWh / 1000 = price per kWh
    # The correct ratio for price conversion is from_factor / to_factor
    result = price * (from_factor / to_factor)

    _LOGGER.debug(f"Energy unit conversion: {price} {from_unit} → {result} {to_unit}")
    return result

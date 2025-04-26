"""Utility functions for energy unit and display unit conversions."""
import logging
from typing import Optional

from ..const.energy import EnergyUnit
from ..const.display import DisplayUnit

_LOGGER = logging.getLogger(__name__)

def get_display_unit_multiplier(display_unit: str) -> int:
    """Get the multiplier for converting to the display subunit (e.g., cents).

    Args:
        display_unit: The target display unit (e.g., DisplayUnit.CENTS).

    Returns:
        Multiplier (e.g., 100 for cents) or 1 if no subunit conversion needed.
    """
    if display_unit == DisplayUnit.CENTS:
        return 100
    return 1

def convert_energy_price(
    price: float,
    source_unit: str,
    target_unit: str = EnergyUnit.TARGET, # Default target is kWh
    vat_rate: float = 0.0, # VAT rate (e.g., 0.25 for 25%), defaults to 0
    display_unit_multiplier: int = 1 # Multiplier for subunits (e.g., 100 for cents)
) -> Optional[float]:
    """Convert energy price between units, apply VAT, and adjust for display units.

    Args:
        price: The original price value.
        source_unit: The energy unit of the original price (e.g., EnergyUnit.MWH).
        target_unit: The target energy unit (e.g., EnergyUnit.KWH).
        vat_rate: The VAT rate to apply (0 to 1). Defaults to 0.
        display_unit_multiplier: Multiplier for display subunits (e.g., 100). Defaults to 1.

    Returns:
        The converted price, or None if conversion is not possible.
    """
    if price is None:
        return None

    try:
        # 1. Convert to target energy unit (e.g., MWh to kWh)
        if source_unit != target_unit:
            source_factor = EnergyUnit.CONVERSION.get(source_unit)
            target_factor = EnergyUnit.CONVERSION.get(target_unit)

            if source_factor is None or target_factor is None:
                _LOGGER.error(f"Invalid energy unit specified: source='{source_unit}', target='{target_unit}'")
                return None
            if source_factor == 0:
                _LOGGER.error(f"Source unit '{source_unit}' has a zero conversion factor.")
                return None

            price = price * (target_factor / source_factor)

        # 2. Apply VAT (vat_rate is 0 if VAT is not included)
        price *= (1 + vat_rate)

        # 3. Apply display unit multiplier (e.g., convert EUR to cents)
        price *= display_unit_multiplier

        return price

    except (TypeError, ValueError) as e:
        _LOGGER.error(f"Error during energy price conversion: {e}. Price: {price}, SourceUnit: {source_unit}, TargetUnit: {target_unit}")
        return None

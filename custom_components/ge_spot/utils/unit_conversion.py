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
        # 1. Convert energy units
        # Energy price conversion follows specific rules based on price per unit
        if source_unit != target_unit:
            source_factor = EnergyUnit.CONVERSION.get(source_unit)
            target_factor = EnergyUnit.CONVERSION.get(target_unit)

            if source_factor is None or target_factor is None:
                _LOGGER.error(
                    "Invalid energy unit specified: source='%s', target='%s'",
                    source_unit, target_unit
                )
                return None

            if source_factor == 0:
                _LOGGER.error(
                    "Source unit '%s' has a zero conversion factor.",
                    source_unit
                )
                return None

            # Energy price conversion:
            # Price per MWh to price per kWh: divide by 1000
            # Price per kWh to price per MWh: multiply by 1000
            # This is the correct physics-based conversion for price-per-unit
            if source_unit == EnergyUnit.MWH and target_unit == EnergyUnit.KWH:
                price = price / 1000  # 1 MWh = 1000 kWh, so €/MWh ÷ 1000 = €/kWh
            elif source_unit == EnergyUnit.KWH and target_unit == EnergyUnit.MWH:
                price = price * 1000  # 1 MWh = 1000 kWh, so €/kWh × 1000 = €/MWh
            else:
                # General case - convert using ratio of factors
                price = price * (source_factor / target_factor)

        # 2. Apply VAT
        price *= (1 + vat_rate)

        # 3. Apply display unit multiplier (e.g., for cents)
        price *= display_unit_multiplier

        return price

    except (TypeError, ValueError) as e:
        _LOGGER.error(
            "Error during energy price conversion: %s. Price: %s, SourceUnit: %s, TargetUnit: %s",
            e, price, source_unit, target_unit
        )
        return None

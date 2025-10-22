"""Utility functions for energy unit and display unit conversions."""

import logging
from typing import Optional

from ..const.energy import EnergyUnit
from ..const.display import DisplayUnit

_LOGGER = logging.getLogger(__name__)


def get_display_unit_multiplier(display_unit: str) -> int:
    """Get the multiplier for converting to the display subunit (e.g. cents).

    Args:
        display_unit: The target display unit (e.g. DisplayUnit.CENTS).

    Returns:
        Multiplier (e.g. 100 for cents) or 1 if no subunit conversion needed.
    """
    if display_unit == DisplayUnit.CENTS:
        return 100
    return 1


def convert_energy_price(
    price: float,
    source_unit: str,
    target_unit: str = EnergyUnit.TARGET,  # Default target is kWh
    vat_rate: float = 0.0,  # VAT rate (e.g. 0.25 for 25%), defaults to 0
    display_unit_multiplier: int = 1,  # Multiplier for subunits (e.g. 100 for cents)
    additional_tariff: float = 0.0,  # Additional tariff/fees per kWh, defaults to 0
    energy_tax: float = 0.0,  # Fixed energy tax per kWh (e.g. government levy), defaults to 0
    tariff_in_subunit: bool = False,  # Whether tariff is entered in subunit (cents/øre)
) -> Optional[float]:
    """Convert energy price between units, apply VAT, and adjust for display units.

    Calculation order follows EU tax standards:
    1. Convert energy units (e.g. MWh → kWh)
    2. Add all costs: spot_price + additional_tariff + energy_tax
    3. Apply VAT to total: (spot_price + fees) × (1 + VAT%)
    4. Convert to display unit (e.g. cents)

    Example (Netherlands):
    - Spot: 0.08 EUR/kWh, Tariff: 0.0219 EUR/kWh, Tax: 0.10154 EUR/kWh, VAT: 21%
    - Result: (0.08 + 0.0219 + 0.10154) × 1.21 = 0.246 EUR/kWh

    Args:
        price: The original price value.
        source_unit: The energy unit of the original price (e.g. EnergyUnit.MWH).
        target_unit: The target energy unit (e.g. EnergyUnit.KWH).
        vat_rate: The VAT rate to apply (0 to 1). Defaults to 0.
        display_unit_multiplier: Multiplier for display subunits (e.g. 100). Defaults to 1.
        additional_tariff: Additional tariff/fees from provider (per kWh). Defaults to 0.
        energy_tax: Fixed energy tax per kWh (e.g. government levy). Defaults to 0.
        tariff_in_subunit: If True, tariff is in subunit (cents/øre), else main unit. Defaults to False.

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
                    source_unit,
                    target_unit,
                )
                return None

            if source_factor == 0:
                _LOGGER.error(
                    "Source unit '%s' has a zero conversion factor.", source_unit
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

        # 2. Add additional tariff and energy tax (before VAT)
        # These costs are added to the base price before VAT calculation,
        # following EU standard practice where VAT applies to the total invoice amount.
        # If tariff/tax is entered in subunit (cents/øre), convert to main unit first
        tariff_to_add = additional_tariff
        tax_to_add = energy_tax
        if tariff_in_subunit and display_unit_multiplier > 1:
            tariff_to_add = additional_tariff / display_unit_multiplier
            tax_to_add = energy_tax / display_unit_multiplier
        price += tariff_to_add + tax_to_add

        # 3. Apply VAT (on total: raw price + tariff + tax)
        # VAT is calculated on the sum of all components (spot price + fees + taxes)
        price *= 1 + vat_rate

        # 4. Apply display unit multiplier (e.g. for cents)
        price *= display_unit_multiplier

        return price

    except (TypeError, ValueError) as e:
        _LOGGER.error(
            "Error during energy price conversion: %s. Price: %s, SourceUnit: %s, TargetUnit: %s",
            e,
            price,
            source_unit,
            target_unit,
        )
        return None

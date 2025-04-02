"""Utility functions for currency and unit conversions."""
import logging
from typing import Dict, Optional

from ..const import (
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_MULTIPLIER, 
    CURRENCY_SUBUNIT_NAMES,
    ENERGY_UNIT_CONVERSION
)

_LOGGER = logging.getLogger(__name__)


def get_default_currency(region: str) -> str:
    """Get the default currency for a region."""
    return REGION_TO_CURRENCY.get(region, "EUR")


def convert_to_subunit(value: float, currency: str) -> float:
    """Convert currency value to its subunit (e.g., EUR to cents)."""
    multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(currency, 1)
    return value * multiplier


def get_subunit_name(currency: str) -> str:
    """Get the name of a currency's subunit."""
    return CURRENCY_SUBUNIT_NAMES.get(currency, currency)


def format_price(price: float, currency: str, use_subunit: bool = False, precision: int = 3) -> tuple:
    """Format price with the appropriate unit and precision.
    
    Args:
        price: The price value
        currency: Currency code
        use_subunit: Whether to use subunit (cents, öre, etc.)
        precision: Decimal precision
        
    Returns:
        Tuple of (formatted_price, unit)
    """
    if use_subunit:
        price = convert_to_subunit(price, currency)
        unit = get_subunit_name(currency)
        precision = max(0, precision - 2)  # Reduce precision for subunits
    else:
        unit = currency
    
    return round(price, precision), unit


def convert_energy_price(price: float, from_unit: str = "MWh", to_unit: str = "kWh", vat: float = 0.0) -> float:
    """Convert energy price between units and apply VAT.
    
    Args:
        price: The price value
        from_unit: Source energy unit (default MWh)
        to_unit: Target energy unit (default kWh)
        vat: VAT rate to apply (0.0 = no VAT)
        
    Returns:
        Converted price value
    """
    # Only convert if units are different
    if from_unit != to_unit:
        from_factor = ENERGY_UNIT_CONVERSION.get(from_unit, 1)
        to_factor = ENERGY_UNIT_CONVERSION.get(to_unit, 1)
        
        converted = price * from_factor / to_factor
    else:
        converted = price
    
    # Apply VAT
    if vat > 0:
        converted = converted * (1 + vat)
    
    return converted

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
    currency = REGION_TO_CURRENCY.get(region, "EUR")
    _LOGGER.debug(f"Using default currency for region {region}: {currency}")
    return currency


def convert_to_subunit(value: float, currency: str) -> float:
    """Convert currency value to its subunit (e.g., EUR to cents)."""
    if value is None:
        return None
        
    multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(currency, 1)
    result = value * multiplier
    
    subunit_name = get_subunit_name(currency)
    _LOGGER.debug(f"Converting {value} {currency} to {result} {subunit_name} (multiplier: {multiplier})")
    
    return result


def get_subunit_name(currency: str) -> str:
    """Get the name of a currency's subunit."""
    subunit = CURRENCY_SUBUNIT_NAMES.get(currency, currency)
    return subunit


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
    if price is None:
        return None, currency
        
    original_price = price
    original_unit = currency
    
    if use_subunit:
        price = convert_to_subunit(price, currency)
        unit = get_subunit_name(currency)
        precision = max(0, precision - 2)  # Reduce precision for subunits
    else:
        unit = currency
    
    formatted_price = round(price, precision)
    
    _LOGGER.debug(f"Price formatting: {original_price} {original_unit} → {formatted_price} {unit} (precision: {precision}, use_subunit: {use_subunit})")
    
    return formatted_price, unit


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
    if price is None:
        return None
        
    original_price = price
    
    # Only convert if units are different
    if from_unit != to_unit:
        from_factor = ENERGY_UNIT_CONVERSION.get(from_unit, 1)
        to_factor = ENERGY_UNIT_CONVERSION.get(to_unit, 1)
        
        converted = price * from_factor / to_factor
        _LOGGER.debug(f"Energy unit conversion: {price} {from_unit} → {converted} {to_unit} (factors: {from_unit}={from_factor}, {to_unit}={to_factor})")
    else:
        converted = price
        _LOGGER.debug(f"No energy unit conversion needed (from={from_unit}, to={to_unit})")
    
    # Apply VAT
    result = converted
    if vat > 0:
        result = converted * (1 + vat)
        _LOGGER.debug(f"Applied VAT {vat:.2%}: {converted} → {result}")
    
    _LOGGER.debug(f"Total energy price conversion: {original_price} {from_unit} → {result} {to_unit} with VAT {vat:.2%}")
    
    return result

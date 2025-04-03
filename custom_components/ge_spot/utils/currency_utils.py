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
    """Convert currency value to its subunit (e.g., EUR to cents, SEK to öre)."""
    if value is None:
        return None
        
    multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(currency, 100)
    result = value * multiplier
    
    subunit_name = get_subunit_name(currency)
    _LOGGER.debug(f"Converting {value} {currency} to {result} {subunit_name} (multiplier: {multiplier})")
    
    return result


def get_subunit_name(currency: str) -> str:
    """Get the name of a currency's subunit."""
    subunit = CURRENCY_SUBUNIT_NAMES.get(currency, "cents")
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


def convert_energy_price(price: float, from_unit: str = "MWh", to_unit: str = "kWh", vat: float = 0.0, currency: str = "EUR", target_currency: str = None) -> float:
    """Convert energy price between units, currencies, and apply VAT.
    
    Args:
        price: The price value
        from_unit: Source energy unit (default MWh)
        to_unit: Target energy unit (default kWh)
        vat: VAT rate to apply (0.0 = no VAT)
        currency: Source currency code
        target_currency: Target currency code (if None, no conversion)
        
    Returns:
        Converted price value
    """
    if price is None:
        return None
        
    original_price = price
    _LOGGER.debug(f"Starting conversion: {price} {currency}/{from_unit}")
    
    # Unit conversion (e.g., MWh to kWh)
    if from_unit != to_unit:
        from_factor = ENERGY_UNIT_CONVERSION.get(from_unit, 1)
        to_factor = ENERGY_UNIT_CONVERSION.get(to_unit, 1)
        
        # For MWh to kWh, we divide by 1000
        converted = price / 1000
        _LOGGER.debug(f"Energy unit conversion: {price} {currency}/{from_unit} → {converted} {currency}/{to_unit}")
    else:
        converted = price
        _LOGGER.debug(f"No energy unit conversion needed (from={from_unit}, to={to_unit})")
    
    # Currency conversion if needed
    if target_currency and currency != target_currency:
        # NOTE: Implement proper currency conversion rates here
        # This is a placeholder - actual implementation would depend on having conversion rates
        _LOGGER.debug(f"Currency conversion from {currency} to {target_currency} not implemented")
    
    # Apply VAT
    result = converted
    if vat > 0:
        result = converted * (1 + vat)
        _LOGGER.debug(f"Applied VAT {vat:.2%}: {converted} → {result}")
    
    _LOGGER.debug(f"Total conversion: {original_price} {currency}/{from_unit} → {result} {target_currency or currency}/{to_unit}")
    
    return result


def mwh_to_kwh(price):
    """Convert price from MWh to kWh.
    
    This is a simple division by 1000 since 1 MWh = 1000 kWh.
    """
    if price is None:
        return None
    
    result = price / 1000
    _LOGGER.debug(f"Converting {price} /MWh to {result} /kWh")
    return result


def convert_nordpool_price(price, area=None, apply_vat=True, vat_rate=0.0, 
                          use_subunit=False, currency=None):
    """Convert Nordpool price with proper handling.
    
    Args:
        price: Raw price from Nordpool API (typically in EUR/MWh)
        area: Area code (used to determine currency)
        apply_vat: Whether to apply VAT
        vat_rate: VAT rate to apply
        use_subunit: Whether to convert to subunit (cents, öre)
        currency: Override currency code
    
    Returns:
        Converted price
    """
    from ..const import REGION_TO_CURRENCY, CURRENCY_SUBUNIT_MULTIPLIER, CURRENCY_SUBUNIT_NAMES
    
    if price is None:
        return None
    
    # Step 1: Store original value for logging
    original_price = price
    _LOGGER.debug(f"Starting price conversion: {price} EUR/MWh")
    
    # Step 2: Convert from MWh to kWh (divide by 1000)
    price = mwh_to_kwh(price)
    _LOGGER.debug(f"After MWh to kWh conversion: {price} EUR/kWh")
    
    # Step 3: Apply VAT if requested
    if apply_vat and vat_rate > 0:
        price_before_vat = price
        price = price * (1 + vat_rate)
        _LOGGER.debug(f"After VAT ({vat_rate:.1%}) application: {price_before_vat} → {price}")
    
    # Step 4: Determine currency based on area or override
    target_currency = currency
    if not target_currency and area:
        target_currency = REGION_TO_CURRENCY.get(area, "EUR")
        _LOGGER.debug(f"Using area-specific currency for {area}: {target_currency}")
    
    # Step 5: Convert to subunit if requested
    if use_subunit and target_currency:
        multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(target_currency, 100)
        subunit_name = CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents")
        
        price_before_subunit = price
        price = price * multiplier
        
        _LOGGER.debug(f"After subunit conversion: {price_before_subunit} {target_currency}/kWh → {price} {subunit_name}/kWh (multiplier: {multiplier})")
    
    _LOGGER.debug(f"Final price after all conversions: {original_price} EUR/MWh → {price}")
    return price

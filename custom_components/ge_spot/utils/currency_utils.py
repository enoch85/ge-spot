"""Utility functions for currency and unit conversions."""
import logging
from typing import Dict, Optional
import asyncio

from ..const import (
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_MULTIPLIER, 
    CURRENCY_SUBUNIT_NAMES,
    ENERGY_UNIT_CONVERSION
)
from .exchange_service import get_exchange_service

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
    """Format price with the appropriate unit and precision."""
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


def mwh_to_kwh(price):
    """Convert price from MWh to kWh."""
    if price is None:
        return None
    
    result = price / 1000
    _LOGGER.debug(f"Converting {price} /MWh to {result} /kWh")
    return result


async def async_convert_currency(amount, from_currency, to_currency, session=None):
    """Convert currency asynchronously using exchange service."""
    if from_currency == to_currency or amount is None:
        return amount
        
    try:
        service = await get_exchange_service(session)
        result = await service.convert(amount, from_currency, to_currency)
        _LOGGER.debug(f"Currency conversion: {amount} {from_currency} → {result} {to_currency}")
        return result
    except Exception as e:
        _LOGGER.error(f"Error in currency conversion: {e}")
        # Fall back to the built-in rates
        return _fallback_convert_currency(amount, from_currency, to_currency)


def _fallback_convert_currency(amount, from_currency, to_currency):
    """Fallback currency conversion using fixed rates when exchange service fails."""
    from .exchange_service import FALLBACK_RATES
    
    if from_currency == to_currency or amount is None:
        return amount
        
    try:
        # EUR to other currency
        if from_currency == "EUR" and to_currency in FALLBACK_RATES:
            result = amount * FALLBACK_RATES[to_currency]
            _LOGGER.debug(f"Fallback conversion: {amount} {from_currency} → {result} {to_currency}")
            return result
            
        # Other currency to EUR
        if to_currency == "EUR" and from_currency in FALLBACK_RATES:
            result = amount / FALLBACK_RATES[from_currency]
            _LOGGER.debug(f"Fallback conversion: {amount} {from_currency} → {result} {to_currency}")
            return result
            
        # Between two non-EUR currencies (via EUR)
        if from_currency in FALLBACK_RATES and to_currency in FALLBACK_RATES:
            eur_value = amount / FALLBACK_RATES[from_currency]
            result = eur_value * FALLBACK_RATES[to_currency]
            _LOGGER.debug(f"Fallback conversion: {amount} {from_currency} → {result} {to_currency} (via EUR)")
            return result
    except Exception as e:
        _LOGGER.error(f"Error in fallback currency conversion: {e}")
    
    _LOGGER.warning(f"No exchange rate found for {from_currency} to {to_currency}, returning original amount")
    return amount


async def async_convert_energy_price(price, from_unit="MWh", to_unit="kWh", 
                              from_currency="EUR", to_currency=None, vat=0,
                              to_subunit=False, exchange_rate=None, session=None):
    """
    Comprehensive energy price conversion function.
    
    Args:
        price: The price value to convert
        from_unit: Source energy unit (e.g., "MWh")
        to_unit: Target energy unit (e.g., "kWh")
        from_currency: Source currency (e.g., "EUR")
        to_currency: Target currency (e.g., "SEK")
        vat: VAT rate to apply (0-1)
        to_subunit: Whether to convert to subunit (e.g., SEK → öre)
        exchange_rate: Optional explicit exchange rate to use
        session: Optional aiohttp session to use
        
    Returns:
        Converted price value
    """
    if price is None:
        return None
        
    # Store original value for logging
    original_price = price
    
    # Step 1: Get conversion factors for energy units
    from_factor = ENERGY_UNIT_CONVERSION.get(from_unit, 1)
    to_factor = ENERGY_UNIT_CONVERSION.get(to_unit, 1)
    
    # Step 2: Convert currency if needed
    if from_currency != to_currency and to_currency is not None:
        if exchange_rate is not None:
            # Use provided exchange rate
            price = price * exchange_rate
            _LOGGER.debug(f"Currency conversion using provided rate: {original_price} {from_currency}/{from_unit} → {price} {to_currency}/{from_unit} (rate: {exchange_rate})")
        else:
            # Use exchange service
            price = await async_convert_currency(price, from_currency, to_currency, session)
            _LOGGER.debug(f"Currency conversion via service: {original_price} {from_currency}/{from_unit} → {price} {to_currency}/{from_unit}")
    
    # Step 3: Convert between energy units (e.g., MWh → kWh)
    original_unit_price = price
    price = price * (to_factor / from_factor)
    _LOGGER.debug(f"Energy unit conversion: {original_unit_price} {to_currency or from_currency}/{from_unit} → {price} {to_currency or from_currency}/{to_unit} (factor: {to_factor/from_factor})")
    
    # Step 4: Apply VAT if specified
    pre_vat_price = price
    if vat != 0:
        price = price * (1 + vat)
        _LOGGER.debug(f"VAT application: {pre_vat_price} {to_currency or from_currency}/{to_unit} → {price} {to_currency or from_currency}/{to_unit} (VAT: {vat:.2%})")
    
    # Step 5: Convert to subunit if requested (e.g., SEK → öre)
    if to_subunit:
        pre_subunit_price = price
        multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(to_currency or from_currency, 100)
        price = price * multiplier
        from_unit_name = to_currency or from_currency
        to_unit_name = get_subunit_name(to_currency or from_currency)
        _LOGGER.debug(f"Subunit conversion: {pre_subunit_price} {from_unit_name}/{to_unit} → {price} {to_unit_name}/{to_unit} (multiplier: {multiplier})")
    
    # Final comprehensive log
    currency_str = to_currency or from_currency
    if to_subunit:
        currency_str = get_subunit_name(currency_str)
    _LOGGER.debug(f"Complete conversion: {original_price} {from_currency}/{from_unit} → {price} {currency_str}/{to_unit}")
    
    return price

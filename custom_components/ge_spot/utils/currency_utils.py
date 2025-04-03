"""Utility functions for currency and unit conversions."""
import logging
from typing import Dict, Optional

from ..const import (
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_MULTIPLIER, 
    CURRENCY_SUBUNIT_NAMES
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


async def convert_energy_price(price, from_unit="MWh", to_unit="kWh", 
                             from_currency="EUR", to_currency=None, 
                             vat=0, to_subunit=False, 
                             exchange_rate=None, session=None):
    """
    Convert energy price between units and currencies.
    
    Args:
        price: Price value to convert
        from_unit: Source energy unit (e.g., "MWh")
        to_unit: Target energy unit (e.g., "kWh")
        from_currency: Source currency (e.g., "EUR")
        to_currency: Target currency (e.g., "SEK")
        vat: VAT rate to apply (0-1)
        to_subunit: Whether to convert to subunit (e.g., SEK → öre)
        exchange_rate: Optional explicit exchange rate to use
        session: Optional aiohttp session
    """
    if price is None:
        return None
    
    original_price = price
    
    # Step 1: Convert currency if needed
    if from_currency != to_currency and to_currency is not None:
        if exchange_rate is not None:
            price = price * exchange_rate
            _LOGGER.debug(f"Currency conversion (explicit rate): {original_price} {from_currency} → {price} {to_currency} (rate: {exchange_rate})")
        else:
            try:
                service = await get_exchange_service(session)
                price = await service.convert(price, from_currency, to_currency)
                _LOGGER.debug(f"Currency conversion (service): {original_price} {from_currency} → {price} {to_currency}")
            except Exception as e:
                _LOGGER.error(f"Currency conversion failed: {e}")
                to_currency = from_currency
    
    # Step 2: Convert energy units (MWh to kWh divide by 1000)
    if from_unit == "MWh" and to_unit == "kWh":
        price = price / 1000
        _LOGGER.debug(f"Energy unit conversion: {original_price} {from_currency}/{from_unit} → {price} {to_currency or from_currency}/{to_unit}")
    
    # Step 3: Apply VAT
    if vat > 0:
        price = price * (1 + vat)
        _LOGGER.debug(f"VAT application: {original_price} → {price} (rate: {vat:.2%})")
    
    # Step 4: Convert to subunit if requested
    if to_subunit:
        price = convert_to_subunit(price, to_currency or from_currency)
        _LOGGER.debug(f"Subunit conversion: {original_price} → {price}")
    
    return price


# Async version (wrapper around the main function)
async def async_convert_energy_price(price, **kwargs):
    """Async wrapper for convert_energy_price."""
    return await convert_energy_price(price, **kwargs)

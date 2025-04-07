"""Utility functions for currency and unit conversions."""
import logging
from typing import Dict, Optional

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
    _LOGGER.debug(f"Energy unit conversion: {price} /MWh to {result} /kWh")
    return result


async def convert_energy_price(price, from_unit="MWh", to_unit="kWh",
                             from_currency="EUR", to_currency=None,
                             vat=0, to_subunit=False,
                             exchange_rate=None, session=None):
    """
    Unified energy price conversion function.

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

    Returns:
        Converted price value
    """
    if price is None:
        return None

    # Store original value for logging
    original_price = price
    original_currency = from_currency

    # Step 1: Convert energy units (MWh to kWh)
    if from_unit == "MWh" and to_unit == "kWh":
        price = mwh_to_kwh(price)
        _LOGGER.debug(f"Energy unit conversion: {original_price} {from_currency}/{from_unit} → {price} {from_currency}/{to_unit}")

    # Step 2: Apply currency conversion if needed
    if to_currency is not None and from_currency != to_currency:
        try:
            if exchange_rate is not None:
                # Use provided exchange rate
                converted_price = price * exchange_rate
                _LOGGER.debug(f"Currency conversion using provided rate: {price} {from_currency} → {converted_price} {to_currency} (rate: {exchange_rate})")
                price = converted_price
            else:
                # Use exchange service
                service = await get_exchange_service(session)
                original_price_in_from_currency = price  # Store for logging
                price = await service.convert(price, from_currency, to_currency)
                _LOGGER.debug(f"Currency conversion using service: {original_price_in_from_currency} {from_currency} → {price} {to_currency}")
            
            # Update from_currency to to_currency as we've now converted
            from_currency = to_currency
        except Exception as e:
            _LOGGER.error(f"Currency conversion failed: {e}")
            # Continue without currency conversion instead of raising

    # Step 3: Apply VAT
    if vat > 0:
        pre_vat_price = price
        price = price * (1 + vat)
        _LOGGER.debug(f"VAT application: {pre_vat_price} → {price} (rate: {vat:.2%})")

    # Step 4: Convert to subunit if requested
    if to_subunit:
        pre_subunit_price = price
        price = convert_to_subunit(price, from_currency)
        _LOGGER.debug(f"Subunit conversion: {pre_subunit_price} {from_currency} → {price} {get_subunit_name(from_currency)}")

    _LOGGER.debug(
        f"Complete conversion: {original_price} {original_currency}/{from_unit} → "
        f"{price} {get_subunit_name(from_currency) if to_subunit else from_currency}/{to_unit} "
        f"(VAT: {vat:.2%})"
    )

    return price


# Async version (wrapper around the main function)
async def async_convert_energy_price(price, **kwargs):
    """Async wrapper for convert_energy_price."""
    return await convert_energy_price(price, **kwargs)

"""Core price conversion functionality."""
import logging
from typing import Optional, Dict, Any

from .currency import convert_to_subunit, get_subunit_name
from .energy import convert_energy_unit

_LOGGER = logging.getLogger(__name__)

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
    """
    if price is None:
        return None

    # Store original value for logging
    original_price = price
    original_currency = from_currency

    # Step 1: Convert energy units (MWh to kWh)
    if from_unit != to_unit:
        price = convert_energy_unit(price, from_unit, to_unit)
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
                # Import here to avoid circular imports
                from ..utils.exchange_service import get_exchange_service
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

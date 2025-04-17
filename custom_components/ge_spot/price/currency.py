"""Currency handling functionality."""
import logging
from typing import Tuple, Optional

from ..const.currencies import CurrencyInfo

_LOGGER = logging.getLogger(__name__)

def get_default_currency(region: str) -> str:
    """Get the default currency for a region."""
    currency = CurrencyInfo.REGION_TO_CURRENCY.get(region, "EUR")
    _LOGGER.debug(f"Using default currency for region {region}: {currency}")
    return currency

def convert_to_subunit(value: float, currency: str) -> float:
    """Convert currency value to its subunit (e.g., EUR to cents, SEK to öre)."""
    if value is None:
        return None

    multiplier = CurrencyInfo.SUBUNIT_MULTIPLIER.get(currency, 100)
    result = value * multiplier

    subunit_name = get_subunit_name(currency)
    _LOGGER.debug(f"Converting {value} {currency} to {result} {subunit_name} (multiplier: {multiplier})")

    return result

def get_subunit_name(currency: str) -> str:
    """Get the name of a currency's subunit."""
    subunit = CurrencyInfo.SUBUNIT_NAMES.get(currency, "cents")
    return subunit

def format_price(price: float, currency: str, use_subunit: bool = False, precision: int = 3) -> Tuple[Optional[float], str]:
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

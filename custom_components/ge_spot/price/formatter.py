"""Formatting utilities for price data."""

import logging

from ..const.currencies import Currency
from .currency_service import format_currency_for_display

_LOGGER = logging.getLogger(__name__)


def format_price(price: float, currency: str, use_subunit: bool = False) -> str:
    """Format price with currency symbol.

    Args:
        price: Price value
        currency: Currency code
        use_subunit: Whether to use subunit (e.g. cents)

    Returns:
        Formatted price string
    """
    if price is None:
        return "N/A"

    # Convert to subunit if requested
    if use_subunit and currency != Currency.CENTS:
        # Convert to cents or equivalent
        price = price * 100
        currency = Currency.CENTS

    return format_currency_for_display(price, currency)


def format_price_value(price: float, precision: int = 2) -> str:
    """Format price value without currency symbol.

    Args:
        price: Price value
        precision: Number of decimal places

    Returns:
        Formatted price string
    """
    if price is None:
        return "N/A"

    return f"{price:.{precision}f}"


def format_relative_price(
    price: float,
    reference_price: float,
    currency: str = None,
    use_subunit: bool = False,
) -> str:
    """Format price relative to a reference price.

    Args:
        price: Price value
        reference_price: Reference price value
        currency: Optional currency code
        use_subunit: Whether to use subunit (e.g. cents)

    Returns:
        Formatted relative price string
    """
    if price is None or reference_price is None or reference_price == 0:
        return "N/A"

    # Calculate difference and percentage
    diff = price - reference_price
    percentage = (diff / reference_price) * 100

    # Format the difference
    if currency:
        diff_str = format_price(diff, currency, use_subunit)
    else:
        diff_str = format_price_value(diff)

    # Format the percentage
    percentage_str = f"{percentage:+.1f}%"

    return f"{diff_str} ({percentage_str})"

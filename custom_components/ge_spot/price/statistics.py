"""Statistics utility functions for price calculations."""

from typing import Dict, List, Optional

from ..api.base.data_structure import PriceStatistics


def calculate_statistics(interval_prices: Dict[str, float]) -> PriceStatistics:
    """Calculate price statistics from a dictionary of interval prices.

    Args:
        interval_prices: Dictionary with interval keys (HH:MM) and price values

    Returns:
        PriceStatistics object with min, max, average values and timestamps
    """
    prices = [p for p in interval_prices.values() if p is not None]
    if not prices:
        return PriceStatistics()

    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / len(prices)

    # Find timestamps for min and max prices
    min_timestamp = None
    max_timestamp = None

    for interval_key, price in interval_prices.items():
        if price == min_price and min_timestamp is None:
            # Store the interval key as-is (HH:MM format)
            # The calling code can convert to full timestamp if needed
            min_timestamp = interval_key

        if price == max_price and max_timestamp is None:
            # Store the interval key as-is (HH:MM format)
            max_timestamp = interval_key

        # Stop if we found both
        if min_timestamp and max_timestamp:
            break

    return PriceStatistics(
        avg=avg_price,
        min=min_price,
        max=max_price,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
    )

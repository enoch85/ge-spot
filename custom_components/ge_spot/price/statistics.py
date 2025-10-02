"""Statistics utility functions for price calculations."""
from typing import Dict, List, Optional

from ..api.base.data_structure import PriceStatistics


def calculate_statistics(interval_prices: Dict[str, float]) -> PriceStatistics:
    """Calculate price statistics from a dictionary of interval prices.

    Args:
        interval_prices: Dictionary with interval keys (HH:MM) and price values

    Returns:
        PriceStatistics object with min, max, average, median values
    """
    prices = [p for p in interval_prices.values() if p is not None]
    if not prices:
        return PriceStatistics(complete_data=False)

    prices.sort()
    mid = len(prices) // 2
    # Ensure indices are valid before access
    median = None
    if prices:
        if len(prices) % 2 == 1:
            median = prices[mid]
        elif mid > 0:
            median = (prices[mid - 1] + prices[mid]) / 2
        else:  # Only one element
            median = prices[0]

    return PriceStatistics(
        min=min(prices) if prices else None,
        max=max(prices) if prices else None,
        average=sum(prices) / len(prices) if prices else None,
        median=median,
        complete_data=True  # Assume complete if this function is called
    )

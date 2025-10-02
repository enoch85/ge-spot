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
        return PriceStatistics()

    return PriceStatistics(
        avg=sum(prices) / len(prices) if prices else None,
        min=min(prices) if prices else None,
        max=max(prices) if prices else None
    )

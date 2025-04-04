"""Price statistics utilities for GE-Spot integration."""
from datetime import datetime
from typing import Dict, List, Any, Optional

def find_extrema_with_timestamps(price_data: List[Dict]) -> Dict[str, Any]:
    """Find min/max prices with their timestamps."""
    min_price = None
    min_timestamp = None
    max_price = None
    max_timestamp = None

    for period in price_data:
        if "price" not in period or "start" not in period:
            continue

        price = period["price"]
        timestamp = period["start"]

        if min_price is None or price < min_price:
            min_price = price
            min_timestamp = timestamp

        if max_price is None or price > max_price:
            max_price = price
            max_timestamp = timestamp

    return {
        "min": min_price,
        "min_timestamp": min_timestamp.isoformat() if hasattr(min_timestamp, "isoformat") else min_timestamp,
        "max": max_price,
        "max_timestamp": max_timestamp.isoformat() if hasattr(max_timestamp, "isoformat") else max_timestamp,
    }

def get_price_statistics(price_data: List[Dict]) -> Dict[str, Any]:
    """Calculate comprehensive price statistics."""
    if not price_data:
        return {
            "min": None,
            "min_timestamp": None,
            "max": None,
            "max_timestamp": None,
            "average": None,
            "median": None,
        }

    # Get basic min/max with timestamps
    stats = find_extrema_with_timestamps(price_data)

    # Calculate average
    prices = [p.get("price") for p in price_data if p.get("price") is not None]
    if prices:
        stats["average"] = sum(prices) / len(prices)

        # Calculate median
        sorted_prices = sorted(prices)
        mid = len(sorted_prices) // 2
        if len(sorted_prices) % 2 == 0:
            stats["median"] = (sorted_prices[mid-1] + sorted_prices[mid]) / 2
        else:
            stats["median"] = sorted_prices[mid]
    else:
        stats["average"] = None
        stats["median"] = None

    return stats

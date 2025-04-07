"""Price statistics calculation utilities."""
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

_LOGGER = logging.getLogger(__name__)

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

def get_statistics(price_data: List[Dict]) -> Dict[str, Any]:
    """Calculate statistics for the price data."""
    # Get basic statistics including min/max with timestamps
    stats = get_price_statistics(price_data)

    # Add time-of-day based categorization
    off_peak_1 = []
    peak = []
    off_peak_2 = []

    for period in price_data:
        if "hour" not in period or "price" not in period:
            continue

        hour = period["hour"]
        if 0 <= hour < 8:
            off_peak_1.append(period["price"])
        elif 8 <= hour < 20:
            peak.append(period["price"])
        else:  # 20-24
            off_peak_2.append(period["price"])

    # Add time-of-day averages
    stats.update({
        "off_peak_1": sum(off_peak_1) / len(off_peak_1) if off_peak_1 else None,
        "off_peak_2": sum(off_peak_2) / len(off_peak_2) if off_peak_2 else None,
        "peak": sum(peak) / len(peak) if peak else None,
    })

    return stats

"""Utility module for converting price data between different interval granularities.

Supports:
- Hourly data (60 min) → 15-minute intervals (expand/duplicate)
- 30-minute data → 15-minute intervals (expand/duplicate)
- 5-minute data → 15-minute intervals (aggregate/average)

All conversions are automatic based on source interval detection.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict
from collections import defaultdict

from ..const.time import TimeInterval

_LOGGER = logging.getLogger(__name__)


def convert_to_target_intervals(source_prices: Dict[str, float],
                                source_interval_minutes: int) -> Dict[str, float]:
    """
    Convert price data from any source interval to the configured target interval.

    Automatically handles:
    - Expansion (hourly/30min → 15min): Duplicates prices across finer intervals
    - Aggregation (5min → 15min): Averages prices within target intervals
    - Pass-through (15min → 15min): Returns data as-is

    Args:
        source_prices: Dictionary with ISO timestamp keys and price values
        source_interval_minutes: Granularity of source data (5, 30, or 60)

    Returns:
        Dictionary with ISO timestamp keys for target intervals and prices

    Example (60min → 15min expansion):
        Input:  {"2025-10-03T14:00:00+00:00": 50.0}
        Output: {"2025-10-03T14:00:00+00:00": 50.0,
                 "2025-10-03T14:15:00+00:00": 50.0,
                 "2025-10-03T14:30:00+00:00": 50.0,
                 "2025-10-03T14:45:00+00:00": 50.0}

    Example (5min → 15min aggregation):
        Input:  {"2025-10-03T14:00:00+00:00": 50.0,
                 "2025-10-03T14:05:00+00:00": 51.0,
                 "2025-10-03T14:10:00+00:00": 52.0}
        Output: {"2025-10-03T14:00:00+00:00": 51.0}  # averaged
    """
    target_interval_minutes = TimeInterval.get_interval_minutes()

    # Case 1: Source matches target - no conversion needed
    if source_interval_minutes == target_interval_minutes:
        _LOGGER.debug(f"No conversion needed: source = target = {target_interval_minutes}min")
        return source_prices

    # Case 2: Source is coarser (e.g. 60min or 30min) - expand/duplicate
    if source_interval_minutes > target_interval_minutes:
        return _expand_intervals(source_prices, source_interval_minutes, target_interval_minutes)

    # Case 3: Source is finer (e.g. 5min) - aggregate/average
    return _aggregate_intervals(source_prices, target_interval_minutes)


def _expand_intervals(coarse_prices: Dict[str, float],
                     source_minutes: int,
                     target_minutes: int) -> Dict[str, float]:
    """Expand coarse intervals (60/30min) to finer intervals (15min) by duplication."""
    intervals_per_source = source_minutes // target_minutes
    expanded = {}

    _LOGGER.debug(f"Expanding {len(coarse_prices)} {source_minutes}-min prices "
                  f"to {target_minutes}-min intervals ({intervals_per_source} per source)")

    for iso_timestamp, price in coarse_prices.items():
        try:
            base_dt = datetime.fromisoformat(iso_timestamp)

            # Create all target intervals within this source interval
            for i in range(intervals_per_source):
                offset_minutes = i * target_minutes
                interval_dt = base_dt + timedelta(minutes=offset_minutes)
                expanded[interval_dt.isoformat()] = price

        except Exception as e:
            _LOGGER.warning(f"Failed to expand timestamp {iso_timestamp}: {e}")

    _LOGGER.debug(f"Expanded: {len(coarse_prices)} → {len(expanded)} intervals")
    return expanded


def _aggregate_intervals(fine_prices: Dict[str, float],
                        target_minutes: int) -> Dict[str, float]:
    """Aggregate fine intervals (5min) to coarser intervals (15min) by averaging."""
    interval_groups = defaultdict(list)

    _LOGGER.debug(f"Aggregating {len(fine_prices)} fine-grained prices "
                  f"to {target_minutes}-min intervals")

    for iso_timestamp, price in fine_prices.items():
        try:
            dt = datetime.fromisoformat(iso_timestamp)

            # Round down to target interval boundary
            minute_rounded = (dt.minute // target_minutes) * target_minutes
            interval_dt = dt.replace(minute=minute_rounded, second=0, microsecond=0)
            interval_groups[interval_dt.isoformat()].append(price)

        except Exception as e:
            _LOGGER.warning(f"Failed to aggregate timestamp {iso_timestamp}: {e}")

    # Average prices within each interval
    aggregated = {
        interval: sum(prices) / len(prices)
        for interval, prices in interval_groups.items()
        if prices
    }

    _LOGGER.debug(f"Aggregated: {len(fine_prices)} → {len(aggregated)} intervals")
    return aggregated


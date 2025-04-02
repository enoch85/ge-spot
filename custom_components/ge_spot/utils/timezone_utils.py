"""Timezone utilities for GE-Spot integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional, Union

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


def ensure_timezone_aware(dt_obj: datetime) -> datetime:
    """Ensure a datetime object has timezone information.
    
    Args:
        dt_obj: Datetime object to check
        
    Returns:
        Timezone-aware datetime object (using UTC if original had no timezone)
    """
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=dt_util.UTC)
    return dt_obj


def find_current_price(price_data: List[Any], reference_time: Optional[datetime] = None) -> Optional[float]:
    """Find the current price in a timezone-safe way.
    
    This function works with the INTERVAL namedtuples used in GE-Spot
    
    Args:
        price_data: List of price data entries
        reference_time: Optional time to find price for (defaults to now)
    
    Returns:
        Current price or None if no matching price found
    """
    if not price_data:
        return None
        
    # Use current time if not provided
    if reference_time is None:
        reference_time = dt_util.now()
    
    # Ensure reference time is timezone-aware
    reference_time = ensure_timezone_aware(reference_time)
    
    # Convert to local time for consistent comparison
    reference_local = dt_util.as_local(reference_time)
    local_hour_start = reference_local.replace(minute=0, second=0, microsecond=0)
    
    for item in price_data:
        # Convert price data timestamp to local time for comparison
        item_time = ensure_timezone_aware(item.hour)
        item_local = dt_util.as_local(item_time)
        
        # Compare year, month, day, hour for exact hourly match
        if (item_local.year == local_hour_start.year and
            item_local.month == local_hour_start.month and
            item_local.day == local_hour_start.day and
            item_local.hour == local_hour_start.hour):
            return item.price
            
    _LOGGER.debug(
        "No matching price found for %s in %d price entries", 
        reference_local.isoformat(),
        len(price_data)
    )
    return None


def filter_day_prices(price_data: List[Any], day_offset: int = 0) -> List[Any]:
    """Filter price data to get entries for today or tomorrow.
    
    Args:
        price_data: List of price data entries
        day_offset: 0 for today, 1 for tomorrow, etc.
        
    Returns:
        Filtered price data for the requested day
    """
    if not price_data:
        return []
        
    # Get target date in local timezone
    target_date = dt_util.as_local(
        dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0) + 
        dt_util.dt.timedelta(days=day_offset)
    ).date()
    
    result = []
    for item in price_data:
        item_time = ensure_timezone_aware(item.hour)
        item_local = dt_util.as_local(item_time)
        
        if item_local.date() == target_date:
            result.append(item)
            
    return result

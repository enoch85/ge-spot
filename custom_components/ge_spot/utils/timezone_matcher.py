"""Timezone-safe utility functions for matching price periods with timestamps."""

import logging
from datetime import datetime, date
from typing import Any, List, Optional

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


def find_current_price_period(price_data, reference_time=None):
    """Find the current price period in a timezone-safe way.
    
    Args:
        price_data: List of price data with hour and price attributes
        reference_time: Optional reference time (defaults to now)
        
    Returns:
        The price for the current period or None if not found
    """
    if not price_data:
        return None
        
    if reference_time is None:
        reference_time = dt_util.now()
    
    # Ensure reference time is timezone aware
    if reference_time.tzinfo is None:
        reference_time = dt_util.as_utc(reference_time)
    
    # Convert to local time for matching
    reference_local = dt_util.as_local(reference_time)
    
    # Normalize to hour start for comparison
    current_hour_start = reference_local.replace(minute=0, second=0, microsecond=0)
    
    for item in price_data:
        # Get the period time and ensure it's timezone aware
        period_time = item.hour
        if period_time.tzinfo is None:
            # If no timezone, assume it's in UTC and convert to local
            period_time = dt_util.as_utc(period_time)
        
        # Convert to local time for comparison
        period_local = dt_util.as_local(period_time)
        
        # Match on full datetime components, not just hour
        if (period_local.year == current_hour_start.year and
            period_local.month == current_hour_start.month and
            period_local.day == current_hour_start.day and
            period_local.hour == current_hour_start.hour):
            return item.price
            
    return None


def match_day_periods(price_data, target_date=None):
    """Get price periods for a specific date.
    
    Args:
        price_data: List of price data with hour and price attributes
        target_date: Date to match (defaults to today)
        
    Returns:
        List of price periods for the target date
    """
    if not price_data:
        return []
        
    if target_date is None:
        target_date = dt_util.now().date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()
    
    result = []
    
    for item in price_data:
        # Get the period time and ensure it's timezone aware
        period_time = item.hour
        if period_time.tzinfo is None:
            # If no timezone, assume it's in UTC
            period_time = dt_util.as_utc(period_time)
        
        # Convert to local time for date comparison
        period_local = dt_util.as_local(period_time)
        
        # Compare dates
        if period_local.date() == target_date:
            result.append(item)
    
    return sorted(result, key=lambda x: x.hour)

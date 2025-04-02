"""Timezone utilities for electricity price APIs.

This module provides robust timezone handling for electricity price data,
ensuring correct prices are shown regardless of timezone or DST transitions.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def ensure_timezone_aware(dt_obj: datetime) -> datetime:
    """Ensure a datetime object is timezone-aware, converting to UTC if not.
    
    Args:
        dt_obj: Datetime object to ensure is timezone-aware
        
    Returns:
        Timezone-aware datetime object
    """
    if dt_obj.tzinfo is None:
        return dt_util.as_utc(dt_obj)
    return dt_obj


def find_current_price(
    price_data: List[Dict[str, Any]], 
    reference_time: Optional[datetime] = None
) -> Optional[float]:
    """Find the current price based on price period ranges.
    
    This function is DST-safe and works correctly across all timezones by using
    datetime range comparison rather than simple hour matching.
    
    Args:
        price_data: List of price data with 'start' and 'end' timezone-aware datetimes
        reference_time: Time to find the price for (defaults to now)
    
    Returns:
        The current price or None if not found
    """
    if reference_time is None:
        reference_time = dt_util.now()
    
    for item in price_data:
        start_time = item.get('start')
        end_time = item.get('end')
        
        # Skip missing or malformed data
        if not start_time or not end_time:
            continue
            
        # Ensure timestamps are timezone-aware for comparison
        start_time = ensure_timezone_aware(start_time)
        end_time = ensure_timezone_aware(end_time)
        
        # Use range-based comparison that works with any timezone
        if start_time <= reference_time < end_time:
            return item.get('value')
    
    return None


def parse_api_timestamp(timestamp: Union[str, datetime]) -> datetime:
    """Parse a timestamp from an API response, ensuring it's timezone-aware.
    
    Args:
        timestamp: String timestamp or datetime object
        
    Returns:
        Timezone-aware datetime object
    """
    if isinstance(timestamp, str):
        dt_obj = dt_util.parse_datetime(timestamp)
        if dt_obj is None:
            # If parsing fails, try ISO format with some fixups
            timestamp = timestamp.replace('Z', '+00:00')
            dt_obj = dt_util.parse_datetime(timestamp)
            
        if dt_obj is None:
            # Last resort fallback
            _LOGGER.warning("Could not parse timestamp: %s", timestamp)
            dt_obj = dt_util.utcnow()
    else:
        dt_obj = timestamp
        
    return ensure_timezone_aware(dt_obj)


def process_price_data(
    data: List[Dict[str, Any]], 
    local_timezone: Any
) -> List[Dict[str, Any]]:
    """Process raw API data into normalized, timezone-aware price periods.
    
    Args:
        data: Raw price data from API
        local_timezone: Local timezone for conversion
        
    Returns:
        List of processed price periods with proper timezone information
    """
    processed_data = []
    
    for item in data:
        # Get the start and end times
        start_time = item.get('start') or item.get('start_time')
        end_time = item.get('end') or item.get('end_time')
        price = item.get('value') or item.get('price')
        
        # Skip invalid data
        if not start_time or not end_time or price is None:
            continue
        
        # Parse and ensure timezone awareness
        start_dt = parse_api_timestamp(start_time)
        end_dt = parse_api_timestamp(end_time)
        
        # Convert to local time for easier filtering and display
        local_start = dt_util.as_local(start_dt)
        local_end = dt_util.as_local(end_dt)
        
        processed_data.append({
            'start': local_start,
            'end': local_end,
            'value': float(price),
            'utc_start': start_dt,
            'utc_end': end_dt,
            'day': local_start.date(),
            'hour': local_start.hour,
            'original': item,  # Keep original data for reference
        })
    
    return sorted(processed_data, key=lambda x: x['start'])


def filter_today_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter data to include only today's prices in local time.
    
    Args:
        data: Processed price data
        
    Returns:
        Filtered list containing only today's prices
    """
    today = dt_util.now().date()
    return [item for item in data if item['day'] == today]


def filter_tomorrow_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter data to include only tomorrow's prices in local time.
    
    Args:
        data: Processed price data
        
    Returns:
        Filtered list containing only tomorrow's prices
    """
    tomorrow = dt_util.as_local(dt_util.utcnow() + dt_util.dt.timedelta(days=1)).date()
    return [item for item in data if item['day'] == tomorrow]


def is_tomorrow_valid(data: List[Dict[str, Any]], min_hours: int = 20) -> bool:
    """Check if tomorrow's data is valid (has enough hours).
    
    Args:
        data: Processed price data
        min_hours: Minimum number of hours required to consider data valid
        
    Returns:
        True if tomorrow has at least min_hours price periods
    """
    tomorrow_data = filter_tomorrow_data(data)
    return len(tomorrow_data) >= min_hours


def get_raw_data_for_attributes(
    data: List[Dict[str, Any]], 
    for_tomorrow: bool = False
) -> List[Dict[str, Any]]:
    """Format data for Home Assistant attributes.
    
    Args:
        data: Processed price data
        for_tomorrow: Whether to get tomorrow's data instead of today's
        
    Returns:
        List of formatted price data suitable for attributes
    """
    if for_tomorrow:
        filtered_data = filter_tomorrow_data(data)
    else:
        filtered_data = filter_today_data(data)
    
    return [
        {
            'start': period['start'].isoformat(),
            'end': period['end'].isoformat(),
            'value': period['value'],
        }
        for period in filtered_data
    ]


def get_price_list(
    data: List[Dict[str, Any]], 
    for_tomorrow: bool = False
) -> List[float]:
    """Get a simple list of prices for today or tomorrow.
    
    Args:
        data: Processed price data
        for_tomorrow: Whether to get tomorrow's data instead of today's
        
    Returns:
        List of prices in chronological order
    """
    if for_tomorrow:
        filtered_data = filter_tomorrow_data(data)
    else:
        filtered_data = filter_today_data(data)
    
    return [period['value'] for period in filtered_data]


def get_statistics(
    data: List[Dict[str, Any]], 
    for_tomorrow: bool = False
) -> Dict[str, Any]:
    """Calculate price statistics for a day.
    
    Args:
        data: Processed price data
        for_tomorrow: Whether to get tomorrow's data instead of today's
        
    Returns:
        Dictionary with price statistics
    """
    if for_tomorrow:
        filtered_data = filter_tomorrow_data(data)
    else:
        filtered_data = filter_today_data(data)
    
    if not filtered_data:
        return {
            'min': None,
            'max': None,
            'average': None,
            'off_peak_1': None,
            'off_peak_2': None,
            'peak': None,
        }
    
    prices = [item['value'] for item in filtered_data]
    
    # Group by hour ranges for off-peak and peak calculations
    off_peak_1 = []
    peak = []
    off_peak_2 = []
    
    for item in filtered_data:
        hour = item['hour']
        if 0 <= hour < 8:
            off_peak_1.append(item['value'])
        elif 8 <= hour < 20:
            peak.append(item['value'])
        else:  # 20-24
            off_peak_2.append(item['value'])
    
    return {
        'min': min(prices) if prices else None,
        'max': max(prices) if prices else None,
        'average': sum(prices) / len(prices) if prices else None,
        'off_peak_1': sum(off_peak_1) / len(off_peak_1) if off_peak_1 else None,
        'off_peak_2': sum(off_peak_2) / len(off_peak_2) if off_peak_2 else None,
        'peak': sum(peak) / len(peak) if peak else None,
    }

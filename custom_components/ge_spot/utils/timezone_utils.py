"""Timezone utilities for GE-Spot integration."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util
from ..const import AREA_TIMEZONES

_LOGGER = logging.getLogger(__name__)


def ensure_timezone_aware(dt_obj: datetime) -> datetime:
    """Ensure a datetime object has timezone information."""
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=dt_util.UTC)
    return dt_obj


def convert_to_local_time(dt: datetime, area: str) -> datetime:
    """Convert a datetime to the local time for a given area."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.UTC)
        
    # Get the timezone for this area
    tz_name = AREA_TIMEZONES.get(area, "UTC")
    
    try:
        # Use Home Assistant's timezone utilities
        local_tz = dt_util.get_time_zone(tz_name)
        return dt.astimezone(local_tz)
    except (ImportError, AttributeError):
        # Fallback if dt_utils is not available
        utc_offset = 1
        if tz_name == "Europe/Helsinki" or tz_name == "Europe/Tallinn":
            utc_offset = 2
        elif tz_name == "Europe/Stockholm":
            utc_offset = 1
        return dt.astimezone(datetime.timezone(datetime.timedelta(hours=utc_offset)))


def process_price_data(raw_data: List[Dict], local_tz=None) -> List[Dict]:
    """Process raw price data into a consistent format with proper timezone handling."""
    if not raw_data:
        return []
        
    periods = []
    
    for item in raw_data:
        # Skip entries that don't have the required keys or aren't dictionaries
        if not isinstance(item, dict):
            _LOGGER.warning("Skipping malformed price data: not a dictionary")
            continue
            
        # Check for required keys
        if not all(key in item for key in ["start", "end", "value"]):
            _LOGGER.warning(f"Skipping malformed price data: {item}")
            continue
            
        # Ensure timestamps are timezone-aware
        try:
            start_time = dt_util.parse_datetime(item["start"]) if isinstance(item["start"], str) else item["start"]
            end_time = dt_util.parse_datetime(item["end"]) if isinstance(item["end"], str) else item["end"]
            
            if start_time is None or end_time is None:
                _LOGGER.warning(f"Skipping malformed price data with invalid timestamps: {item}")
                continue
                
            # Ensure timestamps have timezone info
            if start_time.tzinfo is None:
                start_time = dt_util.as_utc(start_time)
            if end_time.tzinfo is None:
                end_time = dt_util.as_utc(end_time)
                
            # Convert to local time if specified
            if local_tz:
                local_start = start_time.astimezone(local_tz)
                local_end = end_time.astimezone(local_tz)
            else:
                local_start = dt_util.as_local(start_time)
                local_end = dt_util.as_local(end_time)
            
            # Ensure price value is a number
            try:
                price = float(item["value"])
            except (ValueError, TypeError):
                _LOGGER.warning(f"Skipping malformed price data with invalid price: {item}")
                continue
                
            periods.append({
                "start": local_start,
                "end": local_end,
                "price": price,
                "utc_start": start_time,
                "utc_end": end_time,
                "day": local_start.date(),
                "hour": local_start.hour,
                "raw": item,
            })
        except Exception as e:
            _LOGGER.warning(f"Error processing price data {item}: {str(e)}")
            continue
        
    return sorted(periods, key=lambda x: x["start"])


def find_current_price(price_data: List[Dict], reference_time: Optional[datetime] = None) -> Optional[float]:
    """Find the current price for a given time."""
    if not price_data:
        return None
        
    if reference_time is None:
        reference_time = dt_util.now()
            
    for period in price_data:
        if period["start"] <= reference_time < period["end"]:
            return period["price"]
                
    return None


def get_prices_for_day(price_data: List[Dict], day_offset: int = 0) -> List[Dict]:
    """Get all prices for a specific day (today + offset)."""
    target_date = dt_util.now().date()
    if day_offset:
        target_date = dt_util.as_local(
            dt_util.utcnow() + timedelta(days=day_offset)
        ).date()
        
    return [p for p in price_data if p["day"] == target_date]


def get_raw_prices_for_day(day_data: List[Dict]) -> List[Dict]:
    """Format price data for Home Assistant attributes."""
    if not day_data:
        return []
        
    result = []
    for period in day_data:
        if "start" not in period or "end" not in period or "price" not in period:
            continue
            
        try:
            result.append({
                "start": period["start"].isoformat(),
                "end": period["end"].isoformat(),
                "price": period["price"],
            })
        except Exception as e:
            _LOGGER.warning(f"Error formatting price period: {str(e)}")
            
    return result


def get_price_list(day_data: List[Dict]) -> List[float]:
    """Get list of prices in chronological order."""
    return [p["price"] for p in day_data if "price" in p]


def get_statistics(price_data: List[Dict]) -> Dict[str, Any]:
    """Calculate statistics for the price data."""
    prices = [p["price"] for p in price_data if "price" in p]
    
    if not prices:
        return {
            "min": None,
            "max": None,
            "average": None,
            "off_peak_1": None,
            "off_peak_2": None,
            "peak": None,
        }
    
    # Group periods by hour ranges
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
    
    return {
        "min": min(prices) if prices else None,
        "max": max(prices) if prices else None,
        "average": sum(prices) / len(prices) if prices else None,
        "off_peak_1": sum(off_peak_1) / len(off_peak_1) if off_peak_1 else None,
        "off_peak_2": sum(off_peak_2) / len(off_peak_2) if off_peak_2 else None,
        "peak": sum(peak) / len(peak) if peak else None,
    }


def is_tomorrow_valid(price_data: List[Dict]) -> bool:
    """Check if tomorrow's data is valid (at least 20 entries)."""
    tomorrow_data = get_prices_for_day(price_data, 1)
    return len(tomorrow_data) >= 20

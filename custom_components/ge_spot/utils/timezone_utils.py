"""Timezone utilities for GE-Spot integration."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant

from ..const import AREA_TIMEZONES

_LOGGER = logging.getLogger(__name__)


def parse_datetime(timestamp_str: str) -> datetime:
    """Parse a datetime string without timezone assumptions.
    
    Handles various API timestamp formats:
    - ISO format with Z suffix
    - ISO format with explicit offset
    - ISO format without timezone
    """
    if not timestamp_str:
        return None
        
    try:
        # Handle UTC indicator (Z)
        if timestamp_str.endswith('Z'):
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            _LOGGER.debug(f"Parsed UTC timestamp: {timestamp_str} → {dt.isoformat()}")
            return dt
            
        # Handle explicit timezone offset
        if '+' in timestamp_str or '-' in timestamp_str:
            dt = datetime.fromisoformat(timestamp_str)
            _LOGGER.debug(f"Parsed timestamp with offset: {timestamp_str} → {dt.isoformat()}")
            return dt
            
        # No timezone specified - don't assume
        dt = datetime.fromisoformat(timestamp_str)
        if dt.tzinfo is None:
            # Mark as UTC initially, will be converted to local later
            dt = dt.replace(tzinfo=dt_util.UTC)
            _LOGGER.debug(f"Added UTC timezone to naive timestamp: {timestamp_str} → {dt.isoformat()}")
        return dt
        
    except (ValueError, TypeError) as e:
        _LOGGER.error(f"Error parsing datetime {timestamp_str}: {e}")
        return dt_util.now()


def ensure_timezone_aware(dt_obj: datetime) -> datetime:
    """Ensure a datetime object has timezone information."""
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=dt_util.UTC)
    return dt_obj


def localize_datetime(dt: datetime, hass: Optional[HomeAssistant] = None) -> datetime:
    """Convert datetime to Home Assistant's configured timezone."""
    if dt is None:
        return dt_util.now()
        
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.UTC)
    
    # Get HA timezone (most accurate)
    if hass:
        local_tz = hass.config.time_zone
        if local_tz:
            tz = dt_util.get_time_zone(local_tz)
            if tz:
                return dt.astimezone(tz)
    
    # Fall back to dt_util's handling
    return dt.astimezone(dt_util.DEFAULT_TIME_ZONE)


def convert_to_local_time(dt: datetime, area: str) -> datetime:
    """Convert a datetime to the local time for a given area."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.UTC)
    
    # Get the timezone for this area
    tz_name = AREA_TIMEZONES.get(area)
    
    # Try with Home Assistant's timezone utilities
    try:
        if tz_name:
            local_tz = dt_util.get_time_zone(tz_name)
            if local_tz:
                return dt.astimezone(local_tz)
    except Exception as e:
        _LOGGER.warning(f"Error converting to timezone {tz_name} for area {area}: {e}")
    
    # Fall back to dt_util's handling
    return dt.astimezone(dt_util.DEFAULT_TIME_ZONE)


def get_local_now(hass: Optional[HomeAssistant] = None) -> datetime:
    """Get current datetime in HA's timezone."""
    if hass:
        now = dt_util.utcnow()
        return localize_datetime(now, hass)
    return dt_util.now()


def find_current_price(price_data: List[Dict], reference_time: Optional[datetime] = None) -> Optional[float]:
    """Find the price for the current period."""
    period = find_current_price_period(price_data, reference_time)
    return period["price"] if period else None


def find_current_price_period(periods: List[Dict], reference_time: Optional[datetime] = None) -> Optional[Dict]:
    """Find price period containing reference time."""
    if not periods:
        return None
    
    if reference_time is None:
        reference_time = dt_util.now()
    
    # Ensure timezone-aware comparison
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    
    _LOGGER.debug(f"Finding price for time: {reference_time.isoformat()} among {len(periods)} periods")
    
    for period in periods:
        start = period.get("start")
        end = period.get("end")
        
        if not start or not end:
            continue
            
        # Ensure timestamps are timezone-aware
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        if end.tzinfo is None:
            end = end.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            
        if start <= reference_time < end:
            _LOGGER.debug(f"Found period: {start.isoformat()} → {end.isoformat()}, price: {period.get('price')}")
            return period
    
    if periods:
        _LOGGER.warning(f"No matching period found. First period: {periods[0]['start'].isoformat()}")
    return None


def process_price_data(raw_data: List[Dict], local_tz=None) -> List[Dict]:
    """Process raw price data into a consistent format with proper timezone handling."""
    if not raw_data:
        return []

    periods = []
    
    for item in raw_data:
        if not isinstance(item, dict):
            continue

        # Handle different API formats
        start_str = item.get("start") or item.get("deliveryStart")
        end_str = item.get("end") or item.get("deliveryEnd")
        price_value = item.get("price") or item.get("value")
        
        if not start_str or price_value is None:
            continue

        try:
            # Parse timestamps properly
            start_time = parse_datetime(start_str)
            end_time = parse_datetime(end_str) if end_str else start_time + timedelta(hours=1)
            
            # Localize to proper timezone
            if local_tz:
                if hasattr(local_tz, 'tzinfo') and local_tz.tzinfo:
                    start_time = start_time.astimezone(local_tz.tzinfo)
                    end_time = end_time.astimezone(local_tz.tzinfo)
                else:
                    start_time = start_time.astimezone(dt_util.DEFAULT_TIME_ZONE)
                    end_time = end_time.astimezone(dt_util.DEFAULT_TIME_ZONE)
            else:
                start_time = dt_util.as_local(start_time)
                end_time = dt_util.as_local(end_time)
            
            # Parse price value
            if not isinstance(price_value, (float, int)):
                price_value = float(price_value)
            
            periods.append({
                "start": start_time,
                "end": end_time,
                "price": price_value,
                "day": start_time.date(),
                "hour": start_time.hour,
                "raw": item,
            })
            
        except Exception as e:
            _LOGGER.warning(f"Error processing price data: {e}")
            continue

    # Sort by start time
    return sorted(periods, key=lambda x: x.get("start"))


def get_prices_for_day(price_data: List[Dict], day_offset: int = 0, hass: Optional[HomeAssistant] = None) -> List[Dict]:
    """Get all prices for a specific day (today + offset)."""
    if hass:
        target_date = get_local_now(hass).date()
    else:
        target_date = dt_util.now().date()
        
    if day_offset:
        target_date += timedelta(days=day_offset)
        
    return [p for p in price_data if p.get("day") == target_date]


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
                "hour": period["start"].hour if "start" in period else None
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


def is_tomorrow_valid(price_data: List[Dict], hass: Optional[HomeAssistant] = None) -> bool:
    """Check if tomorrow's data is valid (at least 20 entries)."""
    tomorrow_data = get_prices_for_day(price_data, 1, hass)
    return len(tomorrow_data) >= 20

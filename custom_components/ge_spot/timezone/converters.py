"""Timezone conversion utilities."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant

from ..const import AREA_TIMEZONES
from .parsers import parse_datetime

_LOGGER = logging.getLogger(__name__)

class TimezoneConstants:
    """Constants for timezone operations."""
    DEFAULT_RESOLUTION_MINUTES = 60
    MIN_VALID_TOMORROW_ENTRIES = 20  # Minimum entries needed to consider tomorrow data valid
    PERIOD_TYPES = {
        "TODAY": "today",
        "TOMORROW": "tomorrow",
        "OTHER": "other"
    }
    DEFAULT_HOUR_FORMAT = "%H:00"

def ensure_timezone_aware(dt_obj: datetime) -> datetime:
    """Ensure a datetime object has timezone information."""
    if dt_obj and dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=dt_util.UTC)
    return dt_obj

def localize_datetime(dt: datetime, hass: Optional[HomeAssistant] = None) -> datetime:
    """Convert datetime to Home Assistant's configured timezone."""
    if dt is None:
        return dt_util.now()

    dt = ensure_timezone_aware(dt)

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
    reference_time = ensure_timezone_aware(reference_time)

    _LOGGER.debug(f"Finding price for time: {reference_time.isoformat()} among {len(periods)} periods")

    # Look for exact match only - no approximations
    for period in periods:
        start = period.get("start")
        end = period.get("end")

        if not start:
            continue

        # Ensure timestamps are timezone-aware
        start = ensure_timezone_aware(start)

        # If end is missing, assume 1 hour duration
        if not end:
            end = start + timedelta(hours=1)
        else:
            end = ensure_timezone_aware(end)

        # Debug timestamp comparison
        _LOGGER.debug(f"Comparing period: {start.isoformat()} - {end.isoformat()} with reference: {reference_time.isoformat()}")

        if start <= reference_time < end:
            _LOGGER.debug(f"Found matching period: {start.isoformat()} → {end.isoformat()}, price: {period.get('price')}")
            return period

    # If still not found, try matching by hour
    current_hour = reference_time.hour
    for period in periods:
        start = period.get("start")
        if start and hasattr(start, "hour") and start.hour == current_hour:
            _LOGGER.debug(f"Found period by hour match: {start.isoformat()}, price: {period.get('price')}")
            return period

    # If we get here, no matching period was found
    if periods:
        first_period = periods[0]
        start = first_period.get("start")
        if start:
            start = ensure_timezone_aware(start)
            _LOGGER.warning(f"No matching period found for {reference_time.isoformat()}. First period: {start.isoformat() if start else 'unknown'}")

    return None

def classify_price_periods(periods: List[Dict], hass: Optional[HomeAssistant] = None) -> Dict[str, List[Dict]]:
    """Classify price periods by date (today, tomorrow, etc.)."""
    if not periods:
        return {
            TimezoneConstants.PERIOD_TYPES["TODAY"]: [],
            TimezoneConstants.PERIOD_TYPES["TOMORROW"]: [],
            TimezoneConstants.PERIOD_TYPES["OTHER"]: []
        }

    # Get reference dates in local timezone
    if hass:
        local_now = dt_util.as_local(dt_util.utcnow())
    else:
        local_now = dt_util.now()

    today = local_now.date()
    tomorrow = today + timedelta(days=1)

    classified = {
        TimezoneConstants.PERIOD_TYPES["TODAY"]: [],
        TimezoneConstants.PERIOD_TYPES["TOMORROW"]: [],
        TimezoneConstants.PERIOD_TYPES["OTHER"]: []
    }

    for period in periods:
        if not period.get("start"):
            continue

        # Ensure datetime is timezone aware
        start = ensure_timezone_aware(period["start"])
        period_date = start.date()

        if period_date == today:
            classified[TimezoneConstants.PERIOD_TYPES["TODAY"]].append(period)
        elif period_date == tomorrow:
            classified[TimezoneConstants.PERIOD_TYPES["TOMORROW"]].append(period)
        else:
            classified[TimezoneConstants.PERIOD_TYPES["OTHER"]].append(period)

    # Sort each list by start time
    for key in classified:
        classified[key] = sorted(classified[key], key=lambda x: x.get("start", dt_util.now()))

    # Debug log with period counts
    _LOGGER.debug(f"Classified periods: today={len(classified[TimezoneConstants.PERIOD_TYPES['TODAY']])}, tomorrow={len(classified[TimezoneConstants.PERIOD_TYPES['TOMORROW']])}, other={len(classified[TimezoneConstants.PERIOD_TYPES['OTHER']])}")

    return classified

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

            # Log the original and parsed timestamps for debugging
            _LOGGER.debug(f"Original timestamp: {start_str} → Parsed: {start_time.isoformat()}")

            # Localize to proper timezone
            if local_tz:
                if hasattr(local_tz, 'tzinfo') and local_tz.tzinfo:
                    start_time = start_time.astimezone(local_tz.tzinfo)
                    end_time = end_time.astimezone(local_tz.tzinfo)
                    _LOGGER.debug(f"Localized to HA timezone: {start_time.isoformat()}")
                else:
                    start_time = start_time.astimezone(dt_util.DEFAULT_TIME_ZONE)
                    end_time = end_time.astimezone(dt_util.DEFAULT_TIME_ZONE)
                    _LOGGER.debug(f"Localized to default timezone: {start_time.isoformat()}")
            else:
                start_time = dt_util.as_local(start_time)
                end_time = dt_util.as_local(end_time)
                _LOGGER.debug(f"Localized as local: {start_time.isoformat()}")

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
                "currency": item.get("currency")
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
        if "start" not in period or "price" not in period:
            continue

        try:
            end_time = period.get("end") or period["start"] + timedelta(hours=1)

            result.append({
                "start": period["start"].isoformat(),
                "end": end_time.isoformat(),
                "price": period["price"],
                "hour": period["start"].hour if "start" in period else None
            })
        except Exception as e:
            _LOGGER.warning(f"Error formatting price period: {str(e)}")

    return result

def get_price_list(day_data: List[Dict]) -> List[float]:
    """Get list of prices in chronological order."""
    return [p["price"] for p in day_data if "price" in p]

def is_tomorrow_valid(price_data: List[Dict], hass: Optional[HomeAssistant] = None) -> bool:
    """Check if tomorrow's data is valid (at least 20 entries)."""
    tomorrow_data = get_prices_for_day(price_data, 1, hass)
    return len(tomorrow_data) >= TimezoneConstants.MIN_VALID_TOMORROW_ENTRIES

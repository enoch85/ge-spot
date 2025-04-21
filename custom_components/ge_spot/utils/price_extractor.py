"""Utility for extracting hourly prices from API responses."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

def ensure_iso_timestamp(timestamp_str: str) -> str:
    """Ensure a timestamp string is in ISO format with timezone information.
    
    Args:
        timestamp_str: The timestamp string to process
        
    Returns:
        ISO format timestamp string with timezone information
    """
    if not timestamp_str:
        return timestamp_str
        
    # Check if timestamp already has timezone info
    has_timezone = (
        timestamp_str.endswith('Z') or 
        '+' in timestamp_str or 
        '-' in timestamp_str[10:]  # Skip date part
    )
    
    if has_timezone:
        # Already has timezone info, just ensure it's in ISO format
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.isoformat()
        except (ValueError, TypeError):
            # If parsing fails, return the original string
            return timestamp_str
    else:
        # No timezone info, add UTC timezone
        try:
            # Try to parse as naive datetime
            dt = datetime.fromisoformat(timestamp_str)
            # Add UTC timezone
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError):
            # If parsing fails, try other formats
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except ValueError:
                    continue
            
            # If all parsing attempts fail, try to add 'Z' for UTC
            if 'T' in timestamp_str:
                return timestamp_str + 'Z'
            return timestamp_str

def parse_hour_from_string(hour_str: str, tomorrow_date=None) -> Tuple[Optional[int], Optional[datetime]]:
    """Parse hour and date from hour string.

    Args:
        hour_str: Hour string in either "HH:00", "tomorrow_HH:00", or ISO format
        tomorrow_date: Optional tomorrow's date for reference

    Returns:
        Tuple of (hour, datetime) where hour is an integer 0-23 and datetime is the full datetime
        if available, or None if not available
    """
    try:
        # Check if this is a tomorrow hour from timezone conversion
        if hour_str.startswith("tomorrow_"):
            # Extract the hour key without the prefix
            hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
            try:
                hour = int(hour_key.split(":")[0])
                if 0 <= hour < 24:  # Only accept valid hours
                    # Create a datetime for tomorrow with this hour
                    if tomorrow_date:
                        dt = datetime.combine(tomorrow_date, datetime.min.time().replace(hour=hour), timezone.utc)
                    else:
                        # Use tomorrow's date from today
                        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
                        dt = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                    return hour, dt
            except (ValueError, IndexError):
                pass

        # Try simple "HH:00" format
        try:
            hour = int(hour_str.split(":")[0])
            if 0 <= hour < 24:
                return hour, None
        except (ValueError, IndexError):
            pass

        # Try ISO format
        if "T" in hour_str:
            # Ensure the timestamp is in ISO format with timezone
            iso_timestamp = ensure_iso_timestamp(hour_str)
            
            # Handle ISO format with timezone
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            return dt.hour, dt
    except Exception as e:
        _LOGGER.debug(f"Error parsing hour string '{hour_str}': {e}")

    # If we get here, we couldn't parse the hour
    _LOGGER.debug(f"Could not parse hour from: {hour_str}")
    return None, None

def extract_hourly_prices(
    entries: List[Dict[str, Any]],
    area: str,
    is_tomorrow: bool = False,
    tz_service = None
) -> Dict[str, float]:
    """Extract hourly prices from API response entries.
    
    Args:
        entries: List of entries from API response
        area: Area code
        is_tomorrow: Whether these entries are for tomorrow
        tz_service: Optional timezone service for advanced timezone handling
        
    Returns:
        Dictionary mapping hour keys to prices
    """
    # Initialize result dictionary
    result = {}
    
    # Get today's and tomorrow's dates in UTC
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    
    # Process each entry
    for entry in entries:
        if not isinstance(entry, dict) or "entryPerArea" not in entry:
            continue
            
        if area not in entry["entryPerArea"]:
            continue
            
        # Extract values
        start_time = entry.get("deliveryStart")
        raw_price = entry["entryPerArea"][area]
        
        if start_time and raw_price is not None:
            try:
                # Ensure start_time is in ISO format with timezone
                iso_start_time = ensure_iso_timestamp(start_time)
                
                # Parse timestamp
                dt = datetime.fromisoformat(iso_start_time.replace('Z', '+00:00'))
                
                # Check if this entry is for today or tomorrow
                entry_date = dt.date()
                
                # More flexible date filtering - allow entries within 1 hour of midnight
                is_near_midnight = (dt.hour == 23 and not is_tomorrow) or (dt.hour == 0 and is_tomorrow)
                date_matches = (is_tomorrow and entry_date == tomorrow) or (not is_tomorrow and entry_date == today)
                
                # Special case for entries near midnight
                if is_near_midnight and not date_matches:
                    # For 23:00 entries that might be tomorrow but we want today
                    if dt.hour == 23 and not is_tomorrow and entry_date == tomorrow:
                        _LOGGER.debug(f"Special case: 23:00 entry with tomorrow's date but we want today")
                        date_matches = True
                    # For 00:00 entries that might be today but we want tomorrow
                    elif dt.hour == 0 and is_tomorrow and entry_date == today:
                        _LOGGER.debug(f"Special case: 00:00 entry with today's date but we want tomorrow")
                        date_matches = True
                
                if date_matches:
                    # Format as simple hour key
                    hour_key = f"{dt.hour:02d}:00"
                    result[hour_key] = float(raw_price)
                    
                    # We no longer store with ISO timestamp to avoid duplicates
                    # result[iso_start_time] = float(raw_price)
                    
                    _LOGGER.debug(f"Added price for hour {hour_key}: {raw_price}")
                else:
                    _LOGGER.debug(f"Skipped entry with date {entry_date} (looking for {'tomorrow' if is_tomorrow else 'today'})")
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Failed to parse timestamp: {start_time} - {e}")
    
    return result

def extract_all_hourly_prices(raw_data: List[Dict]) -> Dict[str, Any]:
    """Extract all hourly prices from raw data without categorizing them.

    Args:
        raw_data: List of data dictionaries from various sources

    Returns:
        Dict of hour_key -> price with all hourly prices from all sources,
        and special keys "today_hourly_prices" and "tomorrow_hourly_prices" if available
    """
    all_hourly_prices = {}
    today_hourly_prices = {}
    tomorrow_hourly_prices = {}
    has_structured_data = False

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        # Extract from today_hourly_prices
        if "today_hourly_prices" in item and isinstance(item["today_hourly_prices"], dict):
            _LOGGER.debug(f"Found today_hourly_prices in raw data: {len(item['today_hourly_prices'])} entries")
            for hour_str, price in item["today_hourly_prices"].items():
                all_hourly_prices[hour_str] = price
                today_hourly_prices[hour_str] = price
            has_structured_data = True

        # Extract from tomorrow_hourly_prices
        if "tomorrow_hourly_prices" in item and isinstance(item["tomorrow_hourly_prices"], dict):
            _LOGGER.debug(f"Found tomorrow_hourly_prices in raw data: {len(item['tomorrow_hourly_prices'])} entries")
            for hour_str, price in item["tomorrow_hourly_prices"].items():
                all_hourly_prices[hour_str] = price
                tomorrow_hourly_prices[hour_str] = price
            has_structured_data = True

        # Extract from prefixed tomorrow prices
        if "tomorrow_prefixed_prices" in item and isinstance(item["tomorrow_prefixed_prices"], dict):
            _LOGGER.debug(f"Found tomorrow_prefixed_prices in raw data: {len(item['tomorrow_prefixed_prices'])} entries")
            for hour_str, price in item["tomorrow_prefixed_prices"].items():
                all_hourly_prices[hour_str] = price
                # Add to tomorrow_hourly_prices without the prefix
                if hour_str.startswith("tomorrow_"):
                    simple_hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
                    tomorrow_hourly_prices[simple_hour_key] = price
            has_structured_data = True

    _LOGGER.debug(f"Extracted {len(all_hourly_prices)} total hourly prices")
    
    # If we have structured data, add it to the result
    if has_structured_data:
        all_hourly_prices["today_hourly_prices"] = today_hourly_prices
        all_hourly_prices["tomorrow_hourly_prices"] = tomorrow_hourly_prices
        _LOGGER.debug(f"Added structured data: today ({len(today_hourly_prices)}), tomorrow ({len(tomorrow_hourly_prices)})")
    
    return all_hourly_prices

def extract_adapter_hourly_prices(raw_data: List[Dict]) -> Tuple[Dict[str, float], Dict[str, datetime]]:
    """Extract hourly prices from raw data for the adapter.

    Args:
        raw_data: List of data dictionaries from various sources

    Returns:
        Tuple of (hourly_prices, dates_by_hour) where hourly_prices is a dict of hour_key -> price
        and dates_by_hour is a dict of hour_key -> datetime
    """
    hourly_prices = {}
    dates_by_hour = {}
    
    # Get today's date for reference
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        # Only process the new format
        if "today_hourly_prices" in item and isinstance(item["today_hourly_prices"], dict):
            # Store formatted hour -> price mapping
            _LOGGER.debug(f"Found today_hourly_prices in raw data: {len(item['today_hourly_prices'])} entries")

            for hour_str, price in item["today_hourly_prices"].items():
                hour, dt = parse_hour_from_string(hour_str, tomorrow)

                if hour is not None:
                    hour_key = f"{hour:02d}:00"
                    hourly_prices[hour_key] = price
                    if dt is not None:
                        dates_by_hour[hour_key] = dt

    _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices: {sorted(hourly_prices.keys())}")
    return hourly_prices, dates_by_hour

def extract_adapter_tomorrow_prices(raw_data: List[Dict]) -> Tuple[Dict[str, float], Dict[str, datetime]]:
    """Extract tomorrow's hourly prices from raw data for the adapter.

    Args:
        raw_data: List of data dictionaries from various sources

    Returns:
        Tuple of (tomorrow_prices, tomorrow_dates_by_hour) where tomorrow_prices is a dict of hour_key -> price
        and tomorrow_dates_by_hour is a dict of hour_key -> datetime
    """
    tomorrow_prices = {}
    tomorrow_dates_by_hour = {}
    
    # Get tomorrow's date for reference
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        # First try the prefixed format which is guaranteed to be recognized
        if "tomorrow_prefixed_prices" in item and isinstance(item["tomorrow_prefixed_prices"], dict):
            # Store formatted hour -> price mapping
            _LOGGER.debug(f"Found tomorrow_prefixed_prices in raw data: {len(item['tomorrow_prefixed_prices'])} entries")
            for hour_str, price in item["tomorrow_prefixed_prices"].items():
                if hour_str.startswith("tomorrow_"):
                    # Extract the hour key without the prefix
                    hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
                    # We can use this directly
                    tomorrow_prices[hour_key] = price

                    # Create a datetime for tomorrow with this hour
                    try:
                        hour = int(hour_key.split(":")[0])
                        dt = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                        tomorrow_dates_by_hour[hour_key] = dt
                    except (ValueError, IndexError):
                        pass

                    _LOGGER.debug(f"Added prefixed tomorrow price: {hour_key} -> {price}")

        # Then try the standard tomorrow_hourly_prices
        elif "tomorrow_hourly_prices" in item and isinstance(item["tomorrow_hourly_prices"], dict):
            # Store formatted hour -> price mapping
            _LOGGER.debug(f"Found tomorrow_hourly_prices in raw data: {len(item['tomorrow_hourly_prices'])} entries")
            for hour_str, price in item["tomorrow_hourly_prices"].items():
                hour, dt = parse_hour_from_string(hour_str, tomorrow)
                if hour is not None:
                    hour_key = f"{hour:02d}:00"
                    tomorrow_prices[hour_key] = price
                    if dt is not None:
                        tomorrow_dates_by_hour[hour_key] = dt
                    _LOGGER.debug(f"Added tomorrow price: {hour_key} -> {price}")

    _LOGGER.debug(f"Extracted {len(tomorrow_prices)} tomorrow prices: {sorted(tomorrow_prices.keys())}")
    return tomorrow_prices, tomorrow_dates_by_hour

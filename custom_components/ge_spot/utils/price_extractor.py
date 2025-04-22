"""Utility for extracting hourly prices from API responses."""
import logging
import re
import json
import importlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)

def ensure_iso_timestamp(timestamp_str: str, api_timezone: Optional[str] = None) -> str:
    """Ensure a timestamp string is in ISO format with timezone information.
    
    Args:
        timestamp_str: The timestamp string to process
        api_timezone: The timezone of the API, used if the timestamp has no timezone info
        
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
        # No timezone info, add the API timezone if provided
        if api_timezone:
            try:
                # Try to parse the timestamp
                dt = datetime.fromisoformat(timestamp_str)
                
                # Add timezone info
                from ..timezone.timezone_utils import get_timezone_object
                tz_obj = get_timezone_object(api_timezone)
                if tz_obj:
                    dt = dt.replace(tzinfo=tz_obj)
                    return dt.isoformat()
                else:
                    # If timezone object not found, raise an error
                    raise ValueError(f"Invalid timezone: {api_timezone}")
            except (ValueError, TypeError) as e:
                # If parsing fails, raise an error
                raise ValueError(f"Failed to parse timestamp {timestamp_str}: {e}")
        else:
            # No API timezone provided, raise an error
            raise ValueError(f"Timestamp {timestamp_str} has no timezone information and no API timezone provided")

def create_iso_timestamp(date, hour: int, tz_name: Optional[str] = None) -> str:
    """Create an ISO timestamp for a given date and hour.
    
    Args:
        date: The date
        hour: The hour (0-23)
        tz_name: The timezone name to use, if None will use the system timezone
        
    Returns:
        ISO format timestamp string with timezone information
    """
    dt = datetime.combine(date, datetime.min.time().replace(hour=hour))
    
    # Add timezone info
    if tz_name:
        from ..timezone.timezone_utils import get_timezone_object
        tz_obj = get_timezone_object(tz_name)
        if tz_obj:
            dt = dt.replace(tzinfo=tz_obj)
        else:
            # If timezone object not found, use default timezone
            from homeassistant.util import dt as dt_util
            dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    else:
        # Use default timezone if no timezone name provided
        from homeassistant.util import dt as dt_util
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    
    return dt.isoformat()

def detect_source(data: Dict[str, Any]) -> Optional[str]:
    """Detect the source of the data based on its structure.
    
    Args:
        data: Raw API response
        
    Returns:
        Source identifier or None if source cannot be detected
    """
    # Check if source is explicitly specified
    if "source" in data:
        source = data["source"]
        if source in Source.ALL:
            return source
    
    # Get raw data - check for raw_data field first
    raw_data = data.get("raw_data", data)
    
    # Try to detect source based on data structure
    if isinstance(raw_data, dict):
        # AEMO format
        if any(key in raw_data for key in ["ELEC_NEM_SUMMARY", "ELEC_NEM_SUMMARY_PRICES"]):
            return Source.AEMO
        
        # Stromligning format
        if "prices" in raw_data and isinstance(raw_data["prices"], (dict, list)):
            # Check if it's Stromligning format
            if isinstance(raw_data["prices"], dict):
                for _, price_obj in raw_data["prices"].items():
                    if isinstance(price_obj, dict) and any(key in price_obj for key in ["value", "total"]):
                        return Source.STROMLIGNING
            elif isinstance(raw_data["prices"], list):
                for price_entry in raw_data["prices"][:5]:  # Check first 5 entries
                    if isinstance(price_entry, dict) and "date" in price_entry and "price" in price_entry:
                        return Source.STROMLIGNING
    
    # Check for ComEd format
    if isinstance(raw_data, list) and len(raw_data) > 0:
        # Check if all items are dictionaries with millisUTC and price
        if all(isinstance(item, dict) for item in raw_data[:min(5, len(raw_data))]):
            if all("millisUTC" in item and "price" in item for item in raw_data[:min(5, len(raw_data))]):
                return Source.COMED
    
    # Check for ENTSO-E XML format
    if isinstance(raw_data, str) and "<Publication_MarketDocument" in raw_data:
        return Source.ENTSOE
    
    # Check for EPEX HTML format
    if isinstance(raw_data, str) and ("<html" in raw_data.lower() or "<!doctype" in raw_data.lower()):
        return Source.EPEX
    
    # Check for OMIE CSV format
    if isinstance(raw_data, str) and ";" in raw_data:
        if "Precio marginal en el sistema español" in raw_data:
            return Source.OMIE
    
    # Check for Nordpool format
    if isinstance(raw_data, dict) and "data" in raw_data:
        if "areas" in raw_data["data"] or "rows" in raw_data["data"]:
            return Source.NORDPOOL
    
    # Check for Energi Data Service format
    if isinstance(raw_data, dict) and "records" in raw_data:
        if isinstance(raw_data["records"], list) and len(raw_data["records"]) > 0:
            if isinstance(raw_data["records"][0], dict) and "HourUTC" in raw_data["records"][0]:
                return Source.ENERGI_DATA_SERVICE
    
    return None

def get_parser_for_source(source: str):
    """Get the parser for a specific source.
    
    Args:
        source: Source identifier
        
    Returns:
        Parser instance or None if not found
    """
    # Map of source identifiers to parser module and class names
    parser_map = {
        Source.AEMO: ("aemo_parser", "AemoParser"),
        Source.COMED: ("comed_parser", "ComedParser"),
        Source.ENERGI_DATA_SERVICE: ("energi_data_parser", "EnergiDataParser"),
        Source.ENTSOE: ("entsoe_parser", "EntsoeParser"),
        Source.EPEX: ("epex_parser", "EpexParser"),
        Source.NORDPOOL: ("nordpool_parser", "NordpoolPriceParser"),
        Source.OMIE: ("omie_parser", "OmieParser"),
        Source.STROMLIGNING: ("stromligning_parser", "StromligningParser")
    }
    
    if source not in parser_map:
        return None
    
    module_name, class_name = parser_map[source]
    
    try:
        # Dynamically import the parser module
        module = importlib.import_module(f"..api.parsers.{module_name}", package="custom_components.ge_spot.utils")
        
        # Get the parser class
        parser_class = getattr(module, class_name)
        
        # Create an instance of the parser
        return parser_class()
    except (ImportError, AttributeError) as e:
        _LOGGER.warning(f"Failed to import parser for source {source}: {e}")
        return None

def extract_prices(data: Union[Dict[str, Any], List[Dict[str, Any]]], area: Optional[str] = None) -> Dict[str, float]:
    """Extract prices from raw data regardless of source.
    
    Args:
        data: Raw API response
        area: Optional area code (only needed for some data formats)
        
    Returns:
        Dictionary mapping ISO timestamps to prices
    """
    hourly_prices = {}
    
    # Handle list input by processing each item
    if isinstance(data, list):
        for item in data:
            item_prices = extract_prices(item, area)
            hourly_prices.update(item_prices)
        return hourly_prices
    
    # If not a dictionary, we can't extract prices
    if not isinstance(data, dict):
        return hourly_prices
    
    # Strategy 1: Direct hourly_prices mapping with ISO timestamps
    if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
        for timestamp, price in data["hourly_prices"].items():
            if isinstance(price, (int, float)):
                # Ensure timestamp is in ISO format
                iso_timestamp = ensure_iso_timestamp(timestamp)
                hourly_prices[iso_timestamp] = float(price)
        return hourly_prices
    
    # Strategy 2: Use specialized parsers based on source detection
    source = detect_source(data)
    if source:
        parser = get_parser_for_source(source)
        if parser:
            try:
                # Special handling for ENTSOE XML data
                if source == Source.ENTSOE:
                    # For ENTSOE, we need to extract the raw XML data from the nested structure
                    # First check if raw_data is directly in the data
                    xml_data = None
                    
                    # Check for raw_data directly in data
                    if "raw_data" in data and isinstance(data["raw_data"], str) and "<Publication_MarketDocument" in data["raw_data"]:
                        xml_data = data["raw_data"]
                        _LOGGER.debug(f"Found ENTSOE XML data directly in data['raw_data']")
                    
                    # Check for nested raw_data structure
                    elif "raw_data" in data and isinstance(data["raw_data"], dict):
                        raw_data_dict = data["raw_data"]
                        
                        # Check if raw_data is in the nested structure
                        if "raw_data" in raw_data_dict and isinstance(raw_data_dict["raw_data"], str) and "<Publication_MarketDocument" in raw_data_dict["raw_data"]:
                            xml_data = raw_data_dict["raw_data"]
                            _LOGGER.debug(f"Found ENTSOE XML data in nested data['raw_data']['raw_data']")
                    
                    # If we found XML data, use the ENTSOE parser directly
                    if xml_data:
                        _LOGGER.debug(f"Using ENTSOE parser directly with XML data")
                        # Use the parser's parse_hourly_prices method with the raw XML data
                        parser_hourly_prices = parser.parse_hourly_prices(xml_data, area or "")
                        
                        # Use the timestamps directly from the parser
                        for hour_key, price in parser_hourly_prices.items():
                            try:
                                # Just use the timestamp as is
                                hourly_prices[hour_key] = float(price)
                            except (ValueError, TypeError, IndexError) as e:
                                _LOGGER.debug(f"Failed to process ENTSOE timestamp: {hour_key} - {e}")
                        
                        if hourly_prices:
                            _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices using ENTSOE parser with raw XML data")
                            return hourly_prices
                
                # Use the parser's parse_hourly_prices method
                parser_hourly_prices = parser.parse_hourly_prices(data, area or "")
                
                # Convert to ISO timestamps if needed, preserving original timezone
                for hour_key, price in parser_hourly_prices.items():
                    try:
                        # Check if hour_key is already an ISO timestamp
                        if 'T' in hour_key and ('+' in hour_key or 'Z' in hour_key):
                            # Already in ISO format with timezone, just ensure it's properly formatted
                            iso_timestamp = ensure_iso_timestamp(hour_key)
                        elif 'T' in hour_key:
                            # Has date but no timezone, assume it's in the API's timezone
                            # Get API timezone from data if available
                            api_timezone = data.get("api_timezone")
                            if api_timezone == "UTC":
                                # If API timezone is UTC, add Z suffix
                                iso_timestamp = hour_key + "Z"
                            else:
                                # For other timezones, we need to parse and format with the correct offset
                                try:
                                    # Try to get timezone object
                                    from ..timezone.timezone_utils import get_timezone_object
                                    tz_obj = get_timezone_object(api_timezone)
                                    if tz_obj:
                                        # Parse the timestamp in the API timezone
                                        dt = datetime.fromisoformat(hour_key)
                                        dt = dt.replace(tzinfo=tz_obj)
                                        # Format as ISO with the correct timezone offset
                                        iso_timestamp = dt.isoformat()
                                    else:
                                        # Log error if timezone object not found
                                        _LOGGER.error(f"Invalid timezone: {api_timezone}")
                                        # Skip this timestamp
                                        continue
                                except (ImportError, ValueError) as e:
                                    # Log error if parsing fails
                                    _LOGGER.error(f"Failed to parse timestamp {hour_key} with timezone {api_timezone}: {e}")
                                    # Skip this timestamp
                                    continue
                        else:
                            # Simple hour format (HH:00), we need to add date and timezone
                            # This is necessary for determining if it's today or tomorrow
                            hour = int(hour_key.split(':')[0])
                            # Use default timezone for today's date
                            from homeassistant.util import dt as dt_util
                            today = datetime.now(dt_util.DEFAULT_TIME_ZONE).date()
                            iso_timestamp = create_iso_timestamp(today, hour)
                        
                        hourly_prices[iso_timestamp] = float(price)
                    except (ValueError, TypeError, IndexError) as e:
                        _LOGGER.debug(f"Failed to convert hour key to ISO timestamp: {hour_key} - {e}")
                
                if hourly_prices:
                    _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices using {source} parser")
                    return hourly_prices
            except Exception as e:
                _LOGGER.warning(f"Error using {source} parser: {e}")
    
    # Strategy 3: Fall back to generic extraction strategies
    # Get raw data - check for raw_data field first
    raw_data = data.get("raw_data", data)
    
    # Log the structure of the raw_data for debugging
    _LOGGER.debug(f"Raw data type: {type(raw_data)}")
    if isinstance(raw_data, dict):
        _LOGGER.debug(f"Raw data keys: {raw_data.keys()}")
    
    # Get today's date for reference using default timezone
    from homeassistant.util import dt as dt_util
    today = datetime.now(dt_util.DEFAULT_TIME_ZONE).date()
    
    # Generic pattern detection for various data structures
    if isinstance(raw_data, dict):
        # Pattern 3.1: Nested structure with today/tomorrow
        if "today" in raw_data and "tomorrow" in raw_data:
            # Extract from both today and tomorrow data
            hourly_prices.update(_extract_from_nested_structure(raw_data["today"], area, data.get("area")))
            hourly_prices.update(_extract_from_nested_structure(raw_data["tomorrow"], area, data.get("area")))
        
        # Pattern 3.2: Array of entries with timestamps and prices
        elif any(key in raw_data for key in ["entries", "multiAreaEntries", "records", "prices", "data", "values"]):
            for key in ["entries", "multiAreaEntries", "records", "prices", "data", "values"]:
                if key in raw_data and isinstance(raw_data[key], list):
                    hourly_prices.update(_extract_from_array(raw_data[key], area, data.get("area"), data))
    
    # Special handling for ComEd format with millisUTC timestamps
    if source == Source.COMED and isinstance(raw_data, list) and len(raw_data) > 0:
        # Check if this is the ComEd format with millisUTC timestamps
        if all(isinstance(item, dict) for item in raw_data[:min(5, len(raw_data))]):
            if all("millisUTC" in item and "price" in item for item in raw_data[:min(5, len(raw_data))]):
                _LOGGER.debug(f"Processing ComEd format with millisUTC timestamps")
                # Group prices by hour to calculate hourly averages
                hour_prices = {}
                
                for entry in raw_data:
                    try:
                        # Convert millisUTC to datetime
                        millis_str = entry["millisUTC"]
                        # Remove any non-numeric characters
                        millis_str = re.sub(r'[^0-9]', '', millis_str)
                        millis = int(millis_str)
                        
                        # Convert to datetime
                        # Use the ComEd timezone from the API constants
                        from ..const.api import SourceTimezone
                        comed_tz = SourceTimezone.API_TIMEZONES.get(Source.COMED)
                        from ..timezone.timezone_utils import get_timezone_object
                        tz_obj = get_timezone_object(comed_tz)
                        if tz_obj:
                            timestamp = datetime.fromtimestamp(millis / 1000, tz=tz_obj)
                        else:
                            # If timezone object not found, use default timezone
                            from homeassistant.util import dt as dt_util
                            timestamp = datetime.fromtimestamp(millis / 1000, tz=dt_util.DEFAULT_TIME_ZONE)
                        
                        # Parse price
                        price_str = entry["price"]
                        # Remove any non-numeric characters except decimal point
                        price_str = re.sub(r'[^0-9.]', '', price_str)
                        price = float(price_str)
                        
                        # Group by hour
                        hour_key = timestamp.replace(minute=0, second=0, microsecond=0)
                        iso_timestamp = hour_key.isoformat()
                        
                        # Add to hour prices
                        if iso_timestamp not in hour_prices:
                            hour_prices[iso_timestamp] = []
                        hour_prices[iso_timestamp].append(price)
                    except (ValueError, TypeError, KeyError) as e:
                        _LOGGER.debug(f"Failed to parse ComEd price: {entry} - {e}")
                
                # Calculate average price for each hour
                for iso_timestamp, prices in hour_prices.items():
                    if prices:
                        hourly_prices[iso_timestamp] = sum(prices) / len(prices)
                        _LOGGER.debug(f"Added hourly price for {iso_timestamp}: {hourly_prices[iso_timestamp]} (average of {len(prices)} values)")
    
    _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices with ISO timestamps")
    return hourly_prices

def _extract_from_nested_structure(data: Dict[str, Any], area: Optional[str] = None, fallback_area: Optional[str] = None) -> Dict[str, float]:
    """Extract prices from a nested data structure."""
    hourly_prices = {}
    
    # Try to extract from common nested structures
    if not isinstance(data, dict):
        return hourly_prices
        
    # Check for arrays of entries
    for key in ["entries", "multiAreaEntries", "records", "prices", "data", "values"]:
        if key in data and isinstance(data[key], list):
            hourly_prices.update(_extract_from_array(data[key], area, fallback_area, data))
    
    # Check for direct hour -> price mappings
    for key in ["hours", "prices", "values"]:
        if key in data and isinstance(data[key], dict):
            for hour_key, price in data[key].items():
                try:
                    # Try to parse as timestamp
                    iso_timestamp = ensure_iso_timestamp(hour_key)
                    hourly_prices[iso_timestamp] = float(price)
                except (ValueError, TypeError):
                    # If not a timestamp, might be an hour number
                    try:
                        hour = int(hour_key)
                        # Use default timezone for today's date
                        from homeassistant.util import dt as dt_util
                        today = datetime.now(dt_util.DEFAULT_TIME_ZONE).date()
                        iso_timestamp = create_iso_timestamp(today, hour)
                        hourly_prices[iso_timestamp] = float(price)
                    except (ValueError, TypeError):
                        continue
    
    return hourly_prices

def _extract_from_array(entries: List[Dict[str, Any]], area: Optional[str] = None, fallback_area: Optional[str] = None, parent_data: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Extract prices from an array of entries."""
    hourly_prices = {}
    
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        
        # Try to extract timestamp and price
        timestamp = None
        price = None
        
        # Check for area-specific prices
        if "entryPerArea" in entry and isinstance(entry["entryPerArea"], dict):
            # If area is specified, use it, otherwise take the first area
            if area and area in entry["entryPerArea"]:
                price = entry["entryPerArea"][area]
            elif fallback_area and fallback_area in entry["entryPerArea"]:
                price = entry["entryPerArea"][fallback_area]
            elif entry["entryPerArea"]:
                # Take the first area's price
                first_area = next(iter(entry["entryPerArea"]))
                price = entry["entryPerArea"][first_area]
        
        # Try different timestamp fields
        for ts_field in ["deliveryStart", "HourUTC", "HourDK", "timestamp", "time", "date", "start", "startTime"]:
            if ts_field in entry:
                timestamp = entry[ts_field]
                break
        
        # If no timestamp found yet, try to find it in nested objects
        if timestamp is None:
            for key, value in entry.items():
                if isinstance(value, dict) and any(ts_field in value for ts_field in ["timestamp", "time", "date"]):
                    for ts_field in ["timestamp", "time", "date"]:
                        if ts_field in value:
                            timestamp = value[ts_field]
                            break
                    if timestamp:
                        break
        
        # If no price found yet, try different price fields
        if price is None:
            for price_field in ["price", "value", "Price", "SpotPriceEUR", "SpotPriceDKK", "amount", "cost"]:
                if price_field in entry and entry[price_field] is not None:
                    price = entry[price_field]
                    
                    # Handle currency conversion if needed
                    if price_field == "SpotPriceDKK":
                        # Approximate conversion
                        price = float(price) / 7.45
                    
                    break
        
        # If still no price found, try to find it in nested objects
        if price is None:
            for key, value in entry.items():
                if isinstance(value, dict) and any(price_field in value for price_field in ["price", "value", "amount"]):
                    for price_field in ["price", "value", "amount"]:
                        if price_field in value and value[price_field] is not None:
                            price = value[price_field]
                            break
                    if price is not None:
                        break
        
        if timestamp and price is not None:
            try:
                # Get API timezone from parent_data if available
                api_timezone = parent_data.get("api_timezone") if isinstance(parent_data, dict) else None
                
                # Ensure timestamp is in ISO format with API timezone
                iso_timestamp = ensure_iso_timestamp(timestamp, api_timezone)
                hourly_prices[iso_timestamp] = float(price)
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Failed to parse timestamp or price: {timestamp}, {price} - {e}")
    
    return hourly_prices

def get_timestamp_date(timestamp_str: str, user_timezone) -> Optional[datetime]:
    """Get the date from a timestamp string."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        dt = dt.astimezone(user_timezone)
        return dt
    except (ValueError, TypeError) as e:
        _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str} - {e}")
        return None

def extract_all_hourly_prices(raw_data: List[Dict[str, Any]]) -> Dict[str, float]:
    """Extract all hourly prices from a list of raw data dictionaries."""
    all_hourly_prices = {}
    
    for data in raw_data:
        # First check if hourly_prices is already extracted
        if "hourly_prices" in data:
            all_hourly_prices.update(data["hourly_prices"])
        elif "raw_data" in data:
            # Extract hourly prices from raw_data
            hourly_prices = extract_prices(data)
            all_hourly_prices.update(hourly_prices)
        else:
            # Extract hourly prices from data itself
            hourly_prices = extract_prices(data)
            all_hourly_prices.update(hourly_prices)
    
    return all_hourly_prices

def extract_adapter_tomorrow_prices(raw_data: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, datetime]]:
    """Extract tomorrow's prices and dates from raw data."""
    tomorrow_prices = {}
    tomorrow_dates_by_hour = {}
    
    for data in raw_data:
        # Extract hourly prices from raw_data
        hourly_prices = extract_prices(data)
        
        # Get tomorrow's date using default timezone
        from homeassistant.util import dt as dt_util
        tomorrow = datetime.now(dt_util.DEFAULT_TIME_ZONE).date() + timedelta(days=1)
        
        # Look for timestamps in hourly_prices that match tomorrow's date
        for timestamp_str, price in hourly_prices.items():
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if dt.date() == tomorrow:
                    hour_key = f"{dt.hour:02d}:00"
                    tomorrow_prices[hour_key] = price
                    tomorrow_dates_by_hour[hour_key] = dt
            except (ValueError, TypeError):
                continue
    
    return tomorrow_prices, tomorrow_dates_by_hour

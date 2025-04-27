"""Parser for OMIE API responses."""
import logging
import csv
from io import StringIO
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
import pytz

from ...const.sources import Source
from ...const.currencies import Currency
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class OmieParser(BasePriceParser):
    """Parser for OMIE API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.OMIE, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse OMIE API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        result = {
            "hourly_prices": {},
            "currency": Currency.EUR,
            "source": Source.OMIE,
            "api_timezone": "Europe/Madrid"  # Default timezone for OMIE
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty OMIE data received")
            return result

        # Extract area from raw_data if available
        if isinstance(raw_data, dict) and "area" in raw_data:
            result["area"] = raw_data["area"]
            # Update timezone based on area
            if raw_data["area"] == "PT":
                result["api_timezone"] = "Europe/Lisbon"

        # Parse CSV data if it's a string
        if isinstance(raw_data, str):
            try:
                self._parse_csv(raw_data, result)
            except Exception as e:
                _LOGGER.warning(f"Failed to parse OMIE CSV: {e}")
        # Handle pre-processed data
        elif isinstance(raw_data, dict):
            # Case 1: Direct hourly_prices dict
            if "hourly_prices" in raw_data and isinstance(raw_data["hourly_prices"], dict):
                result["hourly_prices"] = raw_data["hourly_prices"]
            # Case 2: Single raw_data CSV string
            elif "raw_data" in raw_data and isinstance(raw_data["raw_data"], str):
                try:
                    csv_data = raw_data["raw_data"]
                    target_date = raw_data.get("target_date")
                    if target_date:
                        result["target_date"] = target_date
                    self._parse_csv(csv_data, result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse OMIE raw_data: {e}")
            # Case 3: Dictionary with raw_csv_by_date structure from API
            elif "raw_csv_by_date" in raw_data and isinstance(raw_data["raw_csv_by_date"], dict):
                _LOGGER.debug(f"Parsing raw_csv_by_date structure with {len(raw_data['raw_csv_by_date'])} dates")
                for date_str, csv_content in raw_data["raw_csv_by_date"].items():
                    if isinstance(csv_content, str) and csv_content.strip():
                        try:
                            date_result = dict(result)  # Create a copy for this date
                            date_result["target_date"] = date_str
                            self._parse_csv(csv_content, date_result)
                            # Merge hourly prices into the main result
                            result["hourly_prices"].update(date_result["hourly_prices"])
                        except Exception as e:
                            _LOGGER.warning(f"Failed to parse OMIE CSV for date {date_str}: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        _LOGGER.debug(f"OMIE parser found {len(result['hourly_prices'])} hourly prices")
        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from OMIE API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.EUR,  # Default currency for OMIE
            "timezone": "Europe/Madrid",
            "area": "ES",  # Default area - Spain
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for area information
            if "area" in data:
                metadata["area"] = data["area"]
                
                # Set correct timezone based on area
                if data["area"] == "PT":
                    metadata["timezone"] = "Europe/Lisbon"
            
            # Check for URL information
            if "url" in data:
                metadata["data_source"] = data["url"]
            
            # Check for target date
            if "target_date" in data:
                metadata["target_date"] = data["target_date"]

        return metadata

    def _parse_csv(self, csv_data: str, result: Dict[str, Any]) -> None:
        """Parse CSV data from OMIE.

        Args:
            csv_data: CSV data string
            result: Result dictionary to update
        """
        hourly_prices = {}
        area = result.get("area", "ES")  # Default to Spain
        
        # Determine timezone based on area
        tz_name = "Europe/Lisbon" if area.upper() == "PT" else "Europe/Madrid"
        local_tz = pytz.timezone(tz_name)
        
        try:
            # Read CSV data
            csv_file = StringIO(csv_data)
            
            # Try to detect CSV format - OMIE can change their format
            # First line might be a header or data
            first_line = csv_file.readline().strip()
            csv_file.seek(0)  # Reset to start of file
            
            # Check if this looks like a header
            if ";" in first_line and any(keyword in first_line.lower() for keyword in ["fecha", "date", "hora", "hour"]):
                # This looks like a header - use csv.DictReader
                csv_reader = csv.DictReader(csv_file, delimiter=';')
                self._parse_csv_with_header(csv_reader, hourly_prices, area, local_tz)
            else:
                # No header or unknown format - try to parse line by line
                csv_reader = csv.reader(csv_file, delimiter=';')
                self._parse_csv_without_header(csv_reader, hourly_prices, area, local_tz)
        
        except Exception as e:
            _LOGGER.error(f"Error parsing OMIE CSV data: {e}")
            raise e  # Re-raise to provide better error reporting
        
        # Update result with parsed hourly prices
        result["hourly_prices"].update(hourly_prices)

    def _parse_csv_with_header(self, csv_reader, hourly_prices: Dict[str, float], area: str, local_tz) -> None:
        """Parse CSV data with headers.

        Args:
            csv_reader: CSV reader with headers
            hourly_prices: Dict to update with hourly prices
            area: Area code
            local_tz: Local timezone for the area
        """
        # Look for common column names in OMIE CSV
        date_columns = ["Fecha", "Date", "fecha", "date", "DATA"]
        hour_columns = ["Hora", "Hour", "hora", "hour", "HORA"]
        price_columns_es = ["Precio España", "Price Spain", "precio españa", "price spain", "PRECIO ES", "ESPAÑA"]
        price_columns_pt = ["Precio Portugal", "Price Portugal", "precio portugal", "price portugal", "PRECIO PT", "PORTUGAL"]
        
        # Determine which columns to use
        field_names = csv_reader.fieldnames
        if not field_names:
            _LOGGER.warning("No field names found in CSV header")
            return
            
        _LOGGER.debug(f"Found CSV fields: {field_names}")
        
        # Find date column - case insensitive search
        date_col = None
        for col in date_columns:
            if col in field_names:
                date_col = col
                break
            # Try case-insensitive match
            for existing_col in field_names:
                if existing_col.lower() == col.lower():
                    date_col = existing_col
                    break
            if date_col:
                break
        
        # Find hour column - case insensitive search
        hour_col = None
        for col in hour_columns:
            if col in field_names:
                hour_col = col
                break
            # Try case-insensitive match
            for existing_col in field_names:
                if existing_col.lower() == col.lower():
                    hour_col = existing_col
                    break
            if hour_col:
                break
        
        # Find price column based on area - case insensitive search
        if area.upper() == "PT":
            price_col_lists = [price_columns_pt, price_columns_es]  # Try PT first, then ES as fallback
        else:  # Default to ES
            price_col_lists = [price_columns_es, price_columns_pt]  # Try ES first, then PT as fallback
            
        price_col = None
        for price_cols in price_col_lists:
            for col in price_cols:
                if col in field_names:
                    price_col = col
                    break
                # Try case-insensitive match or partial match
                for existing_col in field_names:
                    if (existing_col.lower() == col.lower() or 
                        col.lower() in existing_col.lower()):
                        price_col = existing_col
                        break
                if price_col:
                    break
            if price_col:
                break
        
        # Log what columns we found
        _LOGGER.debug(f"Using columns - Date: {date_col}, Hour: {hour_col}, Price: {price_col}")
        
        # If we have the required columns, parse the data
        if date_col and hour_col and price_col:
            for row in csv_reader:
                try:
                    # Parse date
                    date_str = row[date_col].strip()
                    
                    # Parse hour (OMIE uses 1-24 format)
                    hour_str = row[hour_col].strip()
                    hour = int(hour_str)
                    
                    # Parse price
                    price_str = row[price_col].strip().replace(',', '.')
                    # Remove any non-numeric characters except decimal point
                    price_str = ''.join(c for c in price_str if c.isdigit() or c == '.')
                    price = float(price_str)
                    
                    # Get date object
                    date_obj = self._parse_date(date_str)
                    if not date_obj:
                        _LOGGER.warning(f"Could not parse date: {date_str}")
                        continue
                        
                    # Adjust hour (OMIE uses 1-24, we need 0-23)
                    next_day = False
                    if hour == 24:
                        hour = 0
                        next_day = True
                        
                    # Create datetime object in local timezone
                    dt = datetime(
                        date_obj.year, 
                        date_obj.month, 
                        date_obj.day, 
                        hour, 
                        0, 
                        0
                    )
                    
                    # Add a day if hour was 24
                    if next_day:
                        dt += timedelta(days=1)
                        
                    # Localize the datetime to the area's timezone
                    dt = local_tz.localize(dt)
                    
                    # Convert to UTC
                    dt_utc = dt.astimezone(pytz.UTC)
                    
                    # Format timestamp in ISO8601 format with Z timezone
                    timestamp = dt_utc.strftime("%Y-%m-%dT%H:%M:%S%z")
                    # Ensure proper ISO8601 format with colon in timezone offset
                    if "+" in timestamp and ":" not in timestamp[-3:]:
                        timestamp = f"{timestamp[:-2]}:{timestamp[-2:]}"
                    
                    # Add to hourly prices
                    hourly_prices[timestamp] = price
                    _LOGGER.debug(f"Added price for {timestamp}: {price}")
                    
                except (ValueError, KeyError) as e:
                    _LOGGER.warning(f"Error parsing OMIE CSV row: {e}, Row: {row}")
        else:
            _LOGGER.warning(f"Missing required columns. Date: {date_col}, Hour: {hour_col}, Price: {price_col}")

    def _parse_csv_without_header(self, csv_reader, hourly_prices: Dict[str, float], area: str, local_tz) -> None:
        """Parse CSV data without headers.

        Args:
            csv_reader: CSV reader without headers
            hourly_prices: Dict to update with hourly prices
            area: Area code
            local_tz: Local timezone for the area
        """
        # Try to parse CSV data without headers
        # OMIE sometimes provides CSV with format: date;hour;es_price;pt_price
        for row in csv_reader:
            if len(row) < 3:
                continue
                
            try:
                # Assume common format: date;hour;es_price;pt_price
                date_str = row[0].strip()
                hour_str = row[1].strip()
                
                # Parse hour (OMIE uses 1-24 format)
                hour = int(hour_str)
                
                # Get price based on area
                if area.upper() == "PT" and len(row) >= 4:
                    price_str = row[3].strip().replace(',', '.')
                else:
                    price_str = row[2].strip().replace(',', '.')
                
                # Remove any non-numeric characters except decimal point
                price_str = ''.join(c for c in price_str if c.isdigit() or c == '.')
                price = float(price_str)
                
                # Get date object
                date_obj = self._parse_date(date_str)
                if not date_obj:
                    _LOGGER.warning(f"Could not parse date: {date_str}")
                    continue
                    
                # Adjust hour (OMIE uses 1-24, we need 0-23)
                next_day = False
                if hour == 24:
                    hour = 0
                    next_day = True
                    
                # Create datetime object in local timezone
                dt = datetime(
                    date_obj.year, 
                    date_obj.month, 
                    date_obj.day, 
                    hour, 
                    0, 
                    0
                )
                
                # Add a day if hour was 24
                if next_day:
                    dt += timedelta(days=1)
                    
                # Localize the datetime to the area's timezone
                dt = local_tz.localize(dt)
                
                # Convert to UTC
                dt_utc = dt.astimezone(pytz.UTC)
                
                # Format timestamp in ISO8601 format with Z timezone
                timestamp = dt_utc.strftime("%Y-%m-%dT%H:%M:%S%z")
                # Ensure proper ISO8601 format with colon in timezone offset
                if "+" in timestamp and ":" not in timestamp[-3:]:
                    timestamp = f"{timestamp[:-2]}:{timestamp[-2:]}"
                
                # Add to hourly prices
                hourly_prices[timestamp] = price
                _LOGGER.debug(f"Added price for {timestamp}: {price}")
                
            except (ValueError, IndexError) as e:
                _LOGGER.warning(f"Error parsing OMIE CSV row without header: {e}, Row: {row}")

    def _parse_date(self, date_str: str) -> Optional[datetime.date]:
        """Parse date string from OMIE.

        Args:
            date_str: Date string

        Returns:
            Date object or None if parsing fails
        """
        if not date_str:
            return None
            
        try:
            # Try various date formats
            formats = [
                "%d/%m/%Y",  # 01/02/2023
                "%Y-%m-%d",   # 2023-02-01
                "%d-%m-%Y",   # 01-02-2023
                "%Y/%m/%d",   # 2023/02/01
                "%d.%m.%Y"    # 01.02.2023
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
                    
            # If standard formats fail, try more aggressive parsing
            # Remove any non-alphanumeric characters and try to interpret
            clean_date = ''.join(c for c in date_str if c.isalnum())
            if len(clean_date) == 8:  # Assuming YYYYMMDD or DDMMYYYY format
                try:
                    # Try YYYYMMDD
                    return datetime.strptime(clean_date, "%Y%m%d").date()
                except ValueError:
                    try:
                        # Try DDMMYYYY
                        return datetime.strptime(clean_date, "%d%m%Y").date()
                    except ValueError:
                        pass
            
            _LOGGER.warning(f"Could not parse date with any format: {date_str}")
        except Exception as e:
            _LOGGER.warning(f"Failed to parse OMIE date: {date_str} - {e}")
            
        return None

    def _get_current_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get current hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Current hour price or None if not available
        """
        if not hourly_prices:
            return None

        # Get current time in UTC
        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Try different timestamp formats
        formats = [
            # Format with Z
            current_hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Format with +00:00
            current_hour.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            # Format with full timezone offset
            current_hour.strftime("%Y-%m-%dT%H:%M:%S%z")
        ]
        
        # Try each format
        for current_hour_key in formats:
            if current_hour_key in hourly_prices:
                return hourly_prices[current_hour_key]
        
        # If no exact match, try to find a timestamp that matches the hour
        hour_prefix = current_hour.strftime("%Y-%m-%dT%H:")
        for ts in hourly_prices.keys():
            if ts.startswith(hour_prefix):
                return hourly_prices[ts]
        
        return None

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None

        # Get next hour in UTC
        now = datetime.now(timezone.utc)
        next_hour = (now.replace(minute=0, second=0, microsecond=0) +
                    timedelta(hours=1))
        
        # Try different timestamp formats
        formats = [
            # Format with Z
            next_hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Format with +00:00
            next_hour.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            # Format with full timezone offset
            next_hour.strftime("%Y-%m-%dT%H:%M:%S%z")
        ]
        
        # Try each format
        for next_hour_key in formats:
            if next_hour_key in hourly_prices:
                return hourly_prices[next_hour_key]
        
        # If no exact match, try to find a timestamp that matches the hour
        hour_prefix = next_hour.strftime("%Y-%m-%dT%H:")
        for ts in hourly_prices.keys():
            if ts.startswith(hour_prefix):
                return hourly_prices[ts]
        
        return None

    def _calculate_day_average(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Day average price or None if not enough data
        """
        if not hourly_prices:
            return None

        # Get today's date in UTC
        today = datetime.now(timezone.utc).date()

        # Filter prices for today
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                # Handle timestamps with and without timezone information
                if hour_key.endswith('Z'):
                    hour_dt = datetime.fromisoformat(hour_key[:-1]).replace(tzinfo=timezone.utc)
                elif '+' in hour_key or '-' in hour_key and not hour_key[-1].isdigit():
                    hour_dt = datetime.fromisoformat(hour_key)
                else:
                    # Assume UTC for timestamps without timezone info
                    hour_dt = datetime.fromisoformat(hour_key).replace(tzinfo=timezone.utc)
                
                if hour_dt.date() == today:
                    today_prices.append(price)
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Error parsing timestamp for day average: {hour_key} - {e}")
                continue

        # Calculate average if we have enough prices
        if len(today_prices) >= 12:
            return sum(today_prices) / len(today_prices)

        return None

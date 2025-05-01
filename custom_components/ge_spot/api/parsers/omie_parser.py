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
            "hourly_raw": {},  # Changed from hourly_prices
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
            # Check if the string looks like JSON
            if raw_data.strip().startswith('{') and raw_data.strip().endswith('}'):
                try:
                    self._parse_json(raw_data, result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse OMIE JSON: {e}")
                    # Fallback to CSV parsing if JSON parsing fails
                    try:
                        self._parse_csv(raw_data, result)
                    except Exception as e2:
                        _LOGGER.warning(f"Failed to parse OMIE CSV: {e2}")
            else:
                try:
                    self._parse_csv(raw_data, result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse OMIE CSV: {e}")
        # Handle pre-processed data
        elif isinstance(raw_data, dict):
            # Case 1: Direct hourly_raw dict
            if "hourly_raw" in raw_data and isinstance(raw_data["hourly_raw"], dict):  # Changed from hourly_prices
                result["hourly_raw"] = raw_data["hourly_raw"]  # Changed from hourly_prices
            # Case 2: Single raw_data CSV or JSON string
            elif "raw_data" in raw_data and isinstance(raw_data["raw_data"], str):
                try:
                    raw_data_str = raw_data["raw_data"]
                    target_date = raw_data.get("target_date")
                    if target_date:
                        result["target_date"] = target_date
                    
                    # Check if the string looks like JSON
                    if raw_data_str.strip().startswith('{') and raw_data_str.strip().endswith('}'):
                        self._parse_json(raw_data_str, result)
                    else:
                        self._parse_csv(raw_data_str, result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse OMIE raw_data: {e}")
            # Case 3: Dictionary with raw_csv_by_date structure from API
            elif "raw_csv_by_date" in raw_data and isinstance(raw_data["raw_csv_by_date"], dict):
                _LOGGER.debug(f"Parsing raw_csv_by_date structure with {len(raw_data['raw_csv_by_date'])} dates")
                for date_str, content in raw_data["raw_csv_by_date"].items():
                    if isinstance(content, str) and content.strip():
                        try:
                            date_result = dict(result)  # Create a copy for this date
                            date_result["target_date"] = date_str
                            
                            # Check if the content looks like JSON
                            if content.strip().startswith('{') and content.strip().endswith('}'):
                                self._parse_json(content, date_result)
                            else:
                                self._parse_csv(content, date_result)
                                
                            # Merge hourly prices into the main result
                            result["hourly_raw"].update(date_result["hourly_raw"])  # Changed from hourly_prices
                        except Exception as e:
                            _LOGGER.warning(f"Failed to parse OMIE data for date {date_str}: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_raw"])  # Changed from hourly_prices
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_raw"])  # Changed from hourly_prices

        _LOGGER.debug(f"OMIE parser found {len(result['hourly_raw'])} hourly prices")  # Changed from hourly_prices
        return result
        
    def _parse_json(self, json_data: str, result: Dict[str, Any]) -> None:
        """Parse JSON data from OMIE.
        
        Args:
            json_data: JSON data string
            result: Result dictionary to update
        """
        hourly_prices = {}
        area = result.get("area", "ES")  # Default to Spain
        
        # Determine timezone based on area
        tz_name = "Europe/Lisbon" if area.upper() == "PT" else "Europe/Madrid"
        local_tz = pytz.timezone(tz_name)
        
        try:
            # Parse JSON data
            data = json.loads(json_data)
            
            # Check for PVPC format (common in ESIOS API)
            if "PVPC" in data and isinstance(data["PVPC"], list):
                pvpc_data = data["PVPC"]
                target_date = result.get("target_date")
                
                for entry in pvpc_data:
                    try:
                        # Extract date and hour
                        day_str = entry.get("Dia")  # Format: DD/MM/YYYY
                        hour_str = entry.get("Hora")  # Format: HH-HH+1
                        
                        if not day_str or not hour_str:
                            continue
                            
                        # Extract price - try different possible fields
                        # PCB is the most common price column for Spain
                        price_str = None
                        for field in ["PCB", "CYM", "PMHPCB", "PMHCYM"]:
                            if field in entry and entry[field]:
                                price_str = entry[field]
                                break
                                
                        if not price_str:
                            continue
                            
                        # Convert price string to float (handle comma as decimal separator)
                        price = float(price_str.replace(",", "."))
                        
                        # Parse the date
                        if "/" in day_str:  # DD/MM/YYYY format
                            day, month, year = map(int, day_str.split("/"))
                        else:  # Fallback to YYYY-MM-DD format
                            year, month, day = map(int, day_str.split("-"))
                            
                        # Parse the hour range and extract start hour
                        start_hour = int(hour_str.split("-")[0])
                        
                        # Create datetime object
                        dt = datetime(year, month, day, start_hour, 0, 0)
                        local_dt = local_tz.localize(dt)
                        utc_dt = local_dt.astimezone(timezone.utc)
                        
                        # Create ISO format timestamp
                        timestamp = utc_dt.isoformat()
                        
                        # Store the price - using direct price assignment without api_price_date
                        hourly_prices[timestamp] = price
                        
                    except (ValueError, KeyError, IndexError) as e:
                        _LOGGER.warning(f"Error parsing PVPC entry: {e}")
                        continue
            
            # Update result with parsed hourly prices
            result["hourly_raw"].update(hourly_prices)  # Changed from hourly_prices
            
            # Add debug log with count of prices extracted
            _LOGGER.debug(f"Parsed {len(hourly_prices)} hourly prices from OMIE JSON data")
            
        except json.JSONDecodeError as e:
            _LOGGER.error(f"Invalid JSON in OMIE data: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Error parsing OMIE JSON data: {e}")
            raise

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

        metadata.update({
            "source": self.source,
            "price_count": len(data.get("hourly_raw", {})),  # Changed from hourly_prices
            "currency": data.get("currency", "EUR"),  # Changed default
            "has_current_price": "current_price" in data and data["current_price"] is not None,
            "has_next_hour_price": "next_hour_price" in data and data["next_hour_price"] is not None,
            "parser_version": "2.1",  # Updated version
            "parsed_at": datetime.now(timezone.utc).isoformat()
        })

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
        result["hourly_raw"].update(hourly_prices)  # Changed from hourly_prices

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
                        dt = dt + timedelta(days=1)
                        
                    # Create localized datetime
                    local_dt = local_tz.localize(dt)
                    
                    # Convert to UTC
                    utc_dt = local_dt.astimezone(timezone.utc)
                    
                    # Create ISO format timestamp
                    timestamp = utc_dt.isoformat()
                    
                    # Store the price directly without api_price_date
                    hourly_prices[timestamp] = price
                    
                except (ValueError, KeyError, IndexError) as e:
                    _LOGGER.warning(f"Error parsing CSV row: {e}")
                    continue
    
    def _parse_date(self, date_str: str) -> Optional[datetime.date]:
        """Parse date string in various formats.

        Args:
            date_str: Date string

        Returns:
            Date object or None if parsing failed
        """
        date_formats = [
            "%d/%m/%Y",  # 25/04/2023
            "%Y-%m-%d",  # 2023-04-25
            "%d-%m-%Y",  # 25-04-2023
            "%d.%m.%Y",  # 25.04.2023
            "%Y/%m/%d",  # 2023/04/25
            "%m/%d/%Y",  # 04/25/2023
            "%d/%m/%y",  # 25/04/23
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
                
        _LOGGER.warning(f"Could not parse date string: {date_str}")
        return None

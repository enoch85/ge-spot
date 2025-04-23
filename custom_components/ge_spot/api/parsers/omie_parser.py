"""Parser for OMIE API responses."""
import logging
import csv
from io import StringIO
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple

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
            "currency": Currency.EUR
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty OMIE data received")
            return result

        # Parse CSV data if it's a string
        if isinstance(raw_data, str):
            try:
                self._parse_csv(raw_data, result)
            except Exception as e:
                _LOGGER.warning(f"Failed to parse OMIE CSV: {e}")
        # Handle pre-processed data
        elif isinstance(raw_data, dict):
            if "hourly_prices" in raw_data and isinstance(raw_data["hourly_prices"], dict):
                result["hourly_prices"] = raw_data["hourly_prices"]
            elif "raw_data" in raw_data and isinstance(raw_data["raw_data"], str):
                try:
                    self._parse_csv(raw_data["raw_data"], result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse OMIE raw_data: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

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
        
        try:
            # Read CSV data
            csv_file = StringIO(csv_data)
            
            # Try to detect CSV format - OMIE can change their format
            # First line might be a header or data
            first_line = csv_file.readline().strip()
            csv_file.seek(0)  # Reset to start of file
            
            # Check if this looks like a header
            if ";" in first_line and ("fecha" in first_line.lower() or "date" in first_line.lower()):
                # This looks like a header - use csv.DictReader
                csv_reader = csv.DictReader(csv_file, delimiter=';')
                self._parse_csv_with_header(csv_reader, hourly_prices, area)
            else:
                # No header or unknown format - try to parse line by line
                csv_reader = csv.reader(csv_file, delimiter=';')
                self._parse_csv_without_header(csv_reader, hourly_prices, area)
        
        except Exception as e:
            _LOGGER.error(f"Error parsing OMIE CSV data: {e}")
        
        # Update result with parsed hourly prices
        result["hourly_prices"].update(hourly_prices)

    def _parse_csv_with_header(self, csv_reader, hourly_prices: Dict[str, float], area: str) -> None:
        """Parse CSV data with headers.

        Args:
            csv_reader: CSV reader with headers
            hourly_prices: Dict to update with hourly prices
            area: Area code
        """
        # Look for common column names in OMIE CSV
        date_columns = ["Fecha", "Date", "fecha", "date", "DATA"]
        hour_columns = ["Hora", "Hour", "hora", "hour", "HORA"]
        price_columns_es = ["Precio España", "Price Spain", "precio españa", "price spain", "PRECIO ES"]
        price_columns_pt = ["Precio Portugal", "Price Portugal", "precio portugal", "price portugal", "PRECIO PT"]
        
        # Determine which columns to use
        field_names = csv_reader.fieldnames
        
        # Find date column
        date_col = next((col for col in date_columns if col in field_names), None)
        
        # Find hour column
        hour_col = next((col for col in hour_columns if col in field_names), None)
        
        # Find price column based on area
        if area.upper() == "PT":
            price_col = next((col for col in price_columns_pt if col in field_names), None)
        else:  # Default to ES
            price_col = next((col for col in price_columns_es if col in field_names), None)
            # If no ES price column found, try PT as fallback
            if not price_col:
                price_col = next((col for col in price_columns_pt if col in field_names), None)
        
        # If we have the required columns, parse the data
        if date_col and hour_col and price_col:
            for row in csv_reader:
                try:
                    # Parse date
                    date_str = row[date_col]
                    
                    # Parse hour (OMIE uses 1-24 format)
                    hour_str = row[hour_col]
                    hour = int(hour_str)
                    
                    # Adjust hour (OMIE uses 1-24, we need 0-23)
                    if hour == 24:
                        hour = 0
                        # Adjust date for hour 24 (which is actually hour 0 of next day)
                        date_obj = self._parse_date(date_str)
                        if date_obj:
                            date_obj += timedelta(days=1)
                            date_str = date_obj.strftime("%Y-%m-%d")
                    
                    # Parse price
                    price_str = row[price_col].replace(',', '.')
                    price = float(price_str)
                    
                    # Create timestamp in ISO format
                    timestamp = f"{date_str}T{hour:02d}:00:00+00:00"
                    
                    # Add to hourly prices
                    hourly_prices[timestamp] = price
                except (ValueError, KeyError) as e:
                    _LOGGER.debug(f"Error parsing OMIE CSV row: {e}")

    def _parse_csv_without_header(self, csv_reader, hourly_prices: Dict[str, float], area: str) -> None:
        """Parse CSV data without headers.

        Args:
            csv_reader: CSV reader without headers
            hourly_prices: Dict to update with hourly prices
            area: Area code
        """
        # Try to parse CSV data without headers
        # OMIE sometimes provides CSV with format: date;hour;es_price;pt_price
        for row in csv_reader:
            if len(row) < 3:
                continue
                
            try:
                # Assume common format: date;hour;es_price;pt_price
                date_str = row[0]
                hour_str = row[1]
                
                # Parse hour (OMIE uses 1-24 format)
                hour = int(hour_str)
                
                # Get price based on area
                if area.upper() == "PT" and len(row) >= 4:
                    price_str = row[3].replace(',', '.')
                else:
                    price_str = row[2].replace(',', '.')
                
                price = float(price_str)
                
                # Adjust hour (OMIE uses 1-24, we need 0-23)
                if hour == 24:
                    hour = 0
                    # Adjust date for hour 24
                    date_obj = self._parse_date(date_str)
                    if date_obj:
                        date_obj += timedelta(days=1)
                        date_str = date_obj.strftime("%Y-%m-%d")
                
                # Create timestamp in ISO format
                timestamp = f"{date_str}T{hour:02d}:00:00+00:00"
                
                # Add to hourly prices
                hourly_prices[timestamp] = price
            except (ValueError, IndexError) as e:
                _LOGGER.debug(f"Error parsing OMIE CSV row without header: {e}")

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
                "%Y/%m/%d"    # 2023/02/01
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        except Exception as e:
            _LOGGER.debug(f"Failed to parse OMIE date: {date_str} - {e}")
            
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

        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_hour_key = current_hour.strftime("%Y-%m-%dT%H:00:00")

        return hourly_prices.get(current_hour_key)

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None

        now = datetime.now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) +
                    timedelta(hours=1))
        next_hour_key = next_hour.strftime("%Y-%m-%dT%H:00:00")

        return hourly_prices.get(next_hour_key)

    def _calculate_day_average(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Day average price or None if not enough data
        """
        if not hourly_prices:
            return None

        # Get today's date
        today = datetime.now().date()

        # Filter prices for today
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                hour_dt = datetime.fromisoformat(hour_key)
                if hour_dt.date() == today:
                    today_prices.append(price)
            except (ValueError, TypeError):
                continue

        # Calculate average if we have enough prices
        if len(today_prices) >= 12:
            return sum(today_prices) / len(today_prices)

        return None

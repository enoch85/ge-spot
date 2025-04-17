"""Parser for OMIE API responses."""
import logging
import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class OmieParser(BasePriceParser):
    """Parser for OMIE API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.OMIE)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OMIE API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "hourly_prices": {},
            "currency": data.get("currency", "EUR"),
            "source": self.source
        }

        # If hourly prices were already processed
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]
        elif "raw_data" in data and isinstance(data["raw_data"], str):
            # OMIE typically returns CSV data
            self._parse_csv(data["raw_data"], result)

        # Add current and next hour prices if available
        if "current_price" in data:
            result["current_price"] = data["current_price"]

        if "next_hour_price" in data:
            result["next_hour_price"] = data["next_hour_price"]

        # Calculate current and next hour prices if not provided
        if "current_price" not in result:
            result["current_price"] = self._get_current_price(result["hourly_prices"])

        if "next_hour_price" not in result:
            result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        # Calculate day average if enough prices
        if len(result["hourly_prices"]) >= 12:
            result["day_average_price"] = self._calculate_day_average(result["hourly_prices"])

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from OMIE API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "EUR",  # Default currency for OMIE
        }

        # If data is a dictionary with metadata
        if isinstance(data, dict):
            # Copy relevant metadata fields
            for field in ["date_str", "target_date", "url"]:
                if field in data:
                    metadata[field] = data[field]

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from OMIE API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

        # If data is a dictionary with raw_data
        if isinstance(data, dict) and "raw_data" in data and isinstance(data["raw_data"], str):
            # Create a temporary result dictionary
            temp_result = {"hourly_prices": {}}

            # Parse CSV data
            self._parse_csv(data["raw_data"], temp_result)

            # Convert ISO format timestamps to hour strings (HH:00)
            for iso_key, price in temp_result["hourly_prices"].items():
                try:
                    # Parse ISO timestamp
                    dt = datetime.fromisoformat(iso_key)
                    # Format as hour string
                    normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                    hour_key = f"{normalized_hour:02d}:00"
                    # Add to hourly prices
                    hourly_prices[hour_key] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to convert ISO timestamp to hour string: {e}")

        return hourly_prices

    def _parse_csv(self, csv_data: str, result: Dict[str, Any]) -> None:
        """Parse OMIE CSV response.

        Args:
            csv_data: CSV data
            result: Result dictionary to update
        """
        # OMIE CSV format can vary, so we'll try different approaches

        # First, try to parse as the tabular format with hours as columns
        if self._parse_tabular_format(csv_data, result):
            return

        # If tabular format fails, try to parse as CSV with header
        try:
            csv_reader = csv.DictReader(StringIO(csv_data), delimiter=';')

            # Look for common field names
            date_fields = ["Fecha", "Date", "DATA", "FECHA"]
            hour_fields = ["Hora", "Hour", "HORA"]
            price_fields = ["Precio", "Price", "PRECIO", "PRICE"]

            for row in csv_reader:
                # Find date field
                date_field = next((f for f in date_fields if f in row), None)
                if not date_field:
                    continue

                # Find hour field
                hour_field = next((f for f in hour_fields if f in row), None)
                if not hour_field:
                    continue

                # Find price field
                price_field = next((f for f in price_fields if f in row), None)
                if not price_field:
                    continue

                try:
                    # Parse date and hour
                    date_str = row[date_field]
                    hour_str = row[hour_field]

                    # Parse timestamp
                    timestamp = self._parse_timestamp(date_str, hour_str)
                    if timestamp:
                        # Format as ISO string for the hour
                        hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                        # Parse price
                        price_str = row[price_field].replace(',', '.')
                        price = float(price_str)

                        # Add to hourly prices
                        result["hourly_prices"][hour_key] = price
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to parse OMIE CSV row: {e}")

        except Exception as e:
            _LOGGER.warning(f"Failed to parse OMIE CSV with header: {e}")

            # If that fails, try to parse as CSV without header
            try:
                csv_reader = csv.reader(StringIO(csv_data), delimiter=';')

                # Skip header row
                next(csv_reader, None)

                for row in csv_reader:
                    if len(row) >= 3:  # Expect at least date, hour, price
                        try:
                            # Parse date and hour
                            date_str = row[0]
                            hour_str = row[1]

                            # Parse timestamp
                            timestamp = self._parse_timestamp(date_str, hour_str)
                            if timestamp:
                                # Format as ISO string for the hour
                                hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                                # Parse price
                                price_str = row[2].replace(',', '.')
                                price = float(price_str)

                                # Add to hourly prices
                                result["hourly_prices"][hour_key] = price
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"Failed to parse OMIE CSV row without header: {e}")

            except Exception as e:
                _LOGGER.warning(f"Failed to parse OMIE CSV without header: {e}")

    def _parse_tabular_format(self, csv_data: str, result: Dict[str, Any]) -> bool:
        """Parse OMIE data in tabular format with hours as columns.

        This handles the format:
        OMIE - Mercado de electricidad;Fecha Emision :13/04/2025 - 01:09;;13/04/2025;...

        ;1;2;3;4;5;6;7;8;9;...;24;
        Precio marginal en el sistema español (EUR/MWh);35,00;35,00;31,30;...

        Args:
            csv_data: CSV data
            result: Result dictionary to update

        Returns:
            True if parsing was successful, False otherwise
        """
        try:
            # Split lines and filter out empty ones
            lines = [line.strip() for line in csv_data.split('\n') if line.strip()]

            if len(lines) < 3:
                return False

            # Extract date from header line
            date_line = lines[0]
            date_str = None

            # Look for a date in DD/MM/YYYY format
            import re
            date_matches = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', date_line)
            if date_matches:
                date_str = date_matches[-1]  # Take the last date in the line

            if not date_str:
                _LOGGER.warning("Could not find date in OMIE tabular data")
                return False

            # Parse the date
            try:
                date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                _LOGGER.warning(f"Could not parse date: {date_str}")
                return False

            # Find the hour header row and price row
            hour_row = None
            price_row = None

            for i, line in enumerate(lines):
                if line.strip().startswith(';1;2;'):
                    hour_row = i
                elif 'Precio marginal en el sistema' in line:
                    price_row = i

            if hour_row is None or price_row is None:
                _LOGGER.warning("Could not find hour header row or price row in OMIE data")
                return False

            # Parse hour headers
            hour_headers = lines[hour_row].split(';')
            # Parse price values
            price_values = lines[price_row].split(';')

            # Check if we have enough data
            if len(hour_headers) < 2 or len(price_values) < 2:
                _LOGGER.warning("Not enough data in OMIE rows")
                return False

            # First column in price row should contain text descriptor
            price_row_header = price_values[0]
            if not price_row_header:
                _LOGGER.warning("Missing price row header")
                return False

            # Create hourly prices
            for i in range(1, min(len(hour_headers), len(price_values))):
                if not hour_headers[i]:
                    continue

                try:
                    # Parse hour
                    hour = int(hour_headers[i])

                    # Parse price (replace comma with dot for decimal)
                    price_str = price_values[i].strip().replace(',', '.')
                    price = float(price_str)

                    # Normalize hour value (subtract 1 because hours are 1-indexed in this format)
                    normalized_hour, adjusted_date = normalize_hour_value(hour-1, date_obj)

                    # Create datetime for this hour
                    dt = datetime.combine(adjusted_date, datetime.min.time()) + timedelta(hours=normalized_hour)

                    # Format as ISO string for the hour
                    hour_key = dt.strftime("%Y-%m-%dT%H:00:00")

                    # Add to hourly prices
                    result["hourly_prices"][hour_key] = price

                except (ValueError, IndexError) as e:
                    _LOGGER.warning(f"Failed to parse hour {hour_headers[i]} or price {price_values[i]}: {e}")

            # Check if we parsed at least some prices
            if result["hourly_prices"]:
                _LOGGER.debug(f"Successfully parsed {len(result['hourly_prices'])} hours from OMIE tabular format")
                return True

            return False

        except Exception as e:
            _LOGGER.warning(f"Failed to parse OMIE tabular format: {e}")
            return False

    def _parse_timestamp(self, date_str: str, hour_str: str) -> Optional[datetime]:
        """Parse timestamp from OMIE format.

        Args:
            date_str: Date string
            hour_str: Hour string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Try to parse date
            date_formats = [
                "%d/%m/%Y",
                "%Y/%m/%d",
                "%d-%m-%Y",
                "%Y-%m-%d"
            ]

            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue

            if not parsed_date:
                return None

            # Try to parse hour
            hour = None

            # Try as integer (e.g., "1", "2", etc.)
            try:
                hour = int(hour_str)
            except ValueError:
                # Try as hour range (e.g., "01-02", "1-2", etc.)
                if '-' in hour_str:
                    try:
                        hour = int(hour_str.split('-')[0])
                    except ValueError:
                        pass

            if hour is None:
                return None

            # Normalize hour value
            normalized_hour, adjusted_date = normalize_hour_value(hour, parsed_date)

            # Create timestamp
            return datetime.combine(adjusted_date, datetime.min.time()) + timedelta(hours=normalized_hour)

        except Exception as e:
            _LOGGER.warning(f"Failed to parse timestamp: {e}")
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

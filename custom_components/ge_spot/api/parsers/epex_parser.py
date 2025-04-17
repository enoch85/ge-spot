"""Parser for EPEX SPOT API responses."""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EpexParser(BasePriceParser):
    """Parser for EPEX SPOT API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.EPEX)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse EPEX SPOT API response.

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
            # EPEX typically returns HTML, which we need to parse
            self._parse_html(data["raw_data"], result)

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
        """Extract metadata from EPEX SPOT API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "EUR",  # Default currency for EPEX
        }

        # If data is a string (HTML), try to parse it
        if isinstance(data, str):
            try:
                # Try to find the delivery date
                date_match = re.search(r'Delivery\s+Date[:\s]+(\d{1,2})[./](\d{1,2})[./](\d{4})', data)
                if date_match:
                    day, month, year = map(int, date_match.groups())
                    metadata["delivery_date"] = f"{year}-{month:02d}-{day:02d}"

                # Try to find the market area
                area_match = re.search(r'Market\s+Area[:\s]+([A-Z0-9_]+)', data)
                if area_match:
                    metadata["market_area"] = area_match.group(1)

            except Exception as e:
                _LOGGER.error(f"Failed to extract metadata from EPEX HTML: {e}")

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from EPEX SPOT API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

        # If data is a string (HTML), try to parse it
        if isinstance(data, str):
            try:
                # Try to find the date
                date_match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', data)
                if date_match:
                    day, month, year = map(int, date_match.groups())
                    base_date = datetime(year, month, day)
                else:
                    # Use today's date if not found
                    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                # Look for hour and price patterns
                # Format: Hour followed by price, e.g., "01-02 | 45.67"
                hour_price_pattern = r'(\d{1,2})(?:-\d{1,2})?\s*[|:]\s*(\d+[.,]\d+)'

                for match in re.finditer(hour_price_pattern, data):
                    try:
                        hour = int(match.group(1))
                        price_str = match.group(2).replace(',', '.')
                        price = float(price_str)

                        # Format as hour string (HH:00)
                        hour_key = f"{hour:02d}:00"

                        # Add to hourly prices
                        hourly_prices[hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse EPEX hour/price: {e}")

                # If we couldn't find prices with the above pattern, try another common format
                if not hourly_prices:
                    # Try table format with hours in rows and prices in cells
                    table_pattern = r'<tr[^>]*>.*?(\d{1,2})[^<]*</td>.*?(\d+[.,]\d+).*?</tr>'

                    for match in re.finditer(table_pattern, data, re.DOTALL):
                        try:
                            hour = int(match.group(1))
                            price_str = match.group(2).replace(',', '.')
                            price = float(price_str)

                            # Format as hour string (HH:00)
                            hour_key = f"{hour:02d}:00"

                            # Add to hourly prices
                            hourly_prices[hour_key] = price
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"Failed to parse EPEX table row: {e}")

            except Exception as e:
                _LOGGER.error(f"Failed to parse hourly prices from EPEX HTML: {e}")

        return hourly_prices

    def _parse_html(self, html_data: str, result: Dict[str, Any]) -> None:
        """Parse EPEX SPOT HTML response.

        Args:
            html_data: HTML data
            result: Result dictionary to update
        """
        # EPEX typically provides data in HTML tables
        # We'll use regex to extract the data

        # Try to find the date
        date_match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', html_data)
        if date_match:
            day, month, year = map(int, date_match.groups())
            base_date = datetime(year, month, day)
        else:
            # Use today's date if not found
            base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Look for hour and price patterns
        # Format: Hour followed by price, e.g., "01-02 | 45.67"
        hour_price_pattern = r'(\d{1,2})(?:-\d{1,2})?\s*[|:]\s*(\d+[.,]\d+)'

        for match in re.finditer(hour_price_pattern, html_data):
            try:
                hour = int(match.group(1))
                price_str = match.group(2).replace(',', '.')
                price = float(price_str)

                try:
                    # Use the utility function to normalize the hour value
                    from ....timezone.timezone_utils import normalize_hour_value
                    normalized_hour, adjusted_date = normalize_hour_value(hour, base_date.date())

                    # Create timestamp with normalized values
                    timestamp = datetime.combine(adjusted_date, datetime.time(hour=normalized_hour))
                except ValueError as e:
                    # Skip invalid hours
                    _LOGGER.warning(f"Skipping invalid hour value in EPEX data: {hour}:00 - {e}")
                    continue

                # Format as ISO string for the hour
                hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                # Add to hourly prices
                result["hourly_prices"][hour_key] = price
            except (ValueError, TypeError) as e:
                if "hour must be in 0..23" in str(e):
                    _LOGGER.error(f"Error converting hour {hour}:00: {e}")
                else:
                    _LOGGER.warning(f"Failed to parse EPEX hour/price: {e}")

        # If we couldn't find prices with the above pattern, try another common format
        if not result["hourly_prices"]:
            # Try table format with hours in rows and prices in cells
            table_pattern = r'<tr[^>]*>.*?(\d{1,2})[^<]*</td>.*?(\d+[.,]\d+).*?</tr>'

            for match in re.finditer(table_pattern, html_data, re.DOTALL):
                try:
                    hour = int(match.group(1))
                    price_str = match.group(2).replace(',', '.')
                    price = float(price_str)

                    try:
                        # Use the utility function to normalize the hour value
                        from ....timezone.timezone_utils import normalize_hour_value
                        normalized_hour, adjusted_date = normalize_hour_value(hour, base_date.date())

                        # Create timestamp with normalized values
                        timestamp = datetime.combine(adjusted_date, datetime.time(hour=normalized_hour))
                    except ValueError as e:
                        # Skip invalid hours
                        _LOGGER.warning(f"Skipping invalid hour value in EPEX data: {hour}:00 - {e}")
                        continue

                    # Format as ISO string for the hour
                    hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                    # Add to hourly prices
                    result["hourly_prices"][hour_key] = price
                except (ValueError, TypeError) as e:
                    if "hour must be in 0..23" in str(e):
                        _LOGGER.error(f"Error converting hour {hour}:00: {e}")
                    else:
                        _LOGGER.warning(f"Failed to parse EPEX table row: {e}")

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

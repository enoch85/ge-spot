"""Parser for EPEX SPOT API responses."""
import logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...const.currencies import Currency
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EpexParser(BasePriceParser):
    """Parser for EPEX SPOT API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.EPEX, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse EPEX SPOT API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        _LOGGER.debug(f"EpexParser received raw_data of type: {type(raw_data)}")
        result = {
            "hourly_prices": {},
            "currency": Currency.EUR
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty EPEX data received")
            _LOGGER.debug(f"EpexParser returning result: {result}")
            return result

        # Parse HTML response if it's a string
        if isinstance(raw_data, str):
            try:
                soup = BeautifulSoup(raw_data, 'html.parser')
                self._parse_html_table(soup, result)
            except Exception as e:
                _LOGGER.warning(f"Failed to parse EPEX HTML: {e}")
        # Handle pre-processed data
        elif isinstance(raw_data, dict):
            if "hourly_prices" in raw_data and isinstance(raw_data["hourly_prices"], dict):
                result["hourly_prices"] = raw_data["hourly_prices"]

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        _LOGGER.debug(f"EpexParser returning result: {result}")
        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from EPEX SPOT API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.EUR,  # Default currency for EPEX
            "timezone": "Europe/Paris",
            "area": "DE",  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for area information
            if "area" in data:
                metadata["area"] = data["area"]

            # Check for market information
            if "modality" in data:
                metadata["market_type"] = data["modality"]

            if "sub_modality" in data:
                metadata["sub_market_type"] = data["sub_modality"]

        return metadata

    def _parse_html_table(self, soup: BeautifulSoup, result: Dict[str, Any]) -> None:
        """Parse HTML table from EPEX SPOT website.

        Args:
            soup: BeautifulSoup object
            result: Result dictionary to update
        """
        # Find the main data table - EPEX has different table formats on their site
        tables = soup.find_all('table', class_='table')
        if not tables:
            # Try alternate table class
            tables = soup.find_all('table', class_='table-01')

        if not tables:
            _LOGGER.warning("No tables found in EPEX HTML")
            return

        # Process all tables to find the price table
        for table in tables:
            try:
                # Check if this is a price table by looking for hour headers
                headers = table.find_all('th')
                hour_headers = [h for h in headers if h.text.strip().endswith(':00') or h.text.strip().replace(' ', '').endswith('h')]

                if hour_headers:
                    # This looks like a price table
                    _LOGGER.debug("Found likely price table in EPEX HTML")

                    # Find rows with prices
                    rows = table.find_all('tr')
                    for row in rows:
                        # Look for cells with price values
                        cells = row.find_all('td')
                        if len(cells) >= 24:  # Typical day has 24 hours
                            # Extract date info
                            date_info = cells[0].text.strip() if cells else None
                            date_obj = self._parse_date(date_info)

                            if not date_obj:
                                continue

                            # Extract prices
                            for hour_idx, cell in enumerate(cells[1:25]):  # Get first 24 hour cells
                                price_text = cell.text.strip().replace(',', '.').replace('N/A', '')
                                if not price_text:
                                    continue

                                try:
                                    # Extract numeric part from price text, e.g. "42.50 €/MWh" -> 42.50
                                    price_value = float(''.join([c for c in price_text if c.isdigit() or c == '.']))

                                    # Create hour key in ISO format
                                    hour_dt = datetime(
                                        date_obj.year, date_obj.month, date_obj.day,
                                        hour_idx, 0, 0, tzinfo=timezone.utc
                                    )
                                    hour_key = hour_dt.isoformat()

                                    # Add to hourly prices
                                    result["hourly_prices"][hour_key] = {"price": price_value, "api_price_date": date_obj.isoformat()}
                                except (ValueError, TypeError) as e:
                                    _LOGGER.debug(f"Failed to parse EPEX price: {price_text} - {e}")
            except Exception as e:
                _LOGGER.debug(f"Error processing EPEX table: {e}")

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        """Parse date string from EPEX SPOT.

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
                "%d.%m.%Y",   # 01.02.2023
                "%Y-%m-%d",   # 2023-02-01
                "%d %b %Y",   # 01 Feb 2023
                "%d %B %Y"    # 01 February 2023
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue

            # If all formats fail, try to extract date parts with regex
            import re
            date_parts = re.findall(r'\d+', date_str)
            if len(date_parts) >= 3:
                # Assume day, month, year order if all parts are numbers
                day = int(date_parts[0])
                month = int(date_parts[1])
                year = int(date_parts[2])
                if year < 100:
                    year += 2000  # Fix 2-digit years
                return datetime(year, month, day).date()
        except Exception as e:
            _LOGGER.debug(f"Failed to parse EPEX date: {date_str} - {e}")

        return None

    def _get_current_price(self, hourly_prices: Dict[str, Dict[str, Any]]) -> Optional[float]:
        """Get current hour price.

        Args:
            hourly_prices: Dictionary of hourly prices {iso_timestamp: {"price": float, ...}}

        Returns:
            Current hour price or None if not available
        """
        if not hourly_prices:
            return None

        # Use UTC time for comparison
        now_utc = datetime.now(timezone.utc)
        current_hour_utc = now_utc.replace(minute=0, second=0, microsecond=0)
        current_hour_key = current_hour_utc.isoformat()

        price_data = hourly_prices.get(current_hour_key)
        return price_data.get("price") if price_data else None

    def _get_next_hour_price(self, hourly_prices: Dict[str, Dict[str, Any]]) -> Optional[float]:
        """Get next hour price.

        Args:
            hourly_prices: Dictionary of hourly prices {iso_timestamp: {"price": float, ...}}

        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None

        # Use UTC time for comparison
        now_utc = datetime.now(timezone.utc)
        next_hour_utc = (now_utc.replace(minute=0, second=0, microsecond=0) +
                         timedelta(hours=1))
        next_hour_key = next_hour_utc.isoformat()

        price_data = hourly_prices.get(next_hour_key)
        return price_data.get("price") if price_data else None

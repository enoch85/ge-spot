"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser
from ...const.currencies import Currency

_LOGGER = logging.getLogger(__name__)

class NordpoolPriceParser(BasePriceParser):
    """Parser for Nordpool API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.NORDPOOL, timezone_service)

    def parse(self, raw_data: Dict[str, Any], area: str = None) -> Dict[str, Any]:
        # Accept both full API response or just a day dict (with multiAreaEntries)
        result = {"hourly_prices": {}, "currency": Currency.EUR}
        area_arg = area
        # If this is just a day dict, wrap it for uniform handling
        if raw_data and "multiAreaEntries" in raw_data:
            day_data = raw_data
            for entry in day_data["multiAreaEntries"]:
                if not isinstance(entry, dict):
                    continue
                ts = entry.get("deliveryStart")
                if not ts:
                    continue
                if not area_arg or "entryPerArea" not in entry or area_arg not in entry["entryPerArea"]:
                    continue
                price = entry["entryPerArea"][area_arg]
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    hour_key = dt.isoformat()
                    price_date = dt.date().isoformat()
                    result["hourly_prices"][hour_key] = {
                        "price": float(price),
                        "api_price_date": price_date
                    }
                except Exception as e:
                    _LOGGER.error(f"Failed to parse timestamp {ts}: {e}")
                    continue
            return result

        # Fallback to super for legacy/other cases
        if not result["hourly_prices"]:
            legacy = super().parse(raw_data)
            if legacy:
                result = legacy
        _LOGGER.debug(f"[NordpoolPriceParser] Parsed hourly_prices keys: {list(result.get('hourly_prices', {}).keys())}")
        return result

    def _parse_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract hourly prices from Nordpool response.

        Args:
            raw_data: Raw API response

        Returns:
            Dict with hourly prices and currency
        """
        result = {
            "hourly_prices": {},
            "currency": self._get_currency(raw_data)
        }

        # Extract data series
        data = raw_data.get("data", {})
        
        # Process the graph series data, which contains the hourly prices
        rows = data.get("Rows", [])
        
        # Each row represents an hour
        for row in rows:
            # Get timestamp from row
            start_time = self._parse_datetime(row.get("StartTime"))
            if not start_time:
                continue
                
            # Get price values for this hour
            columns = row.get("Columns", [])
            if not columns or len(columns) == 0:
                continue
                
            # Typically, the first column contains the price
            price_column = columns[0]
            price_value = self._parse_price(price_column.get("Value"))
            
            if price_value is not None:
                # Format hour as ISO string for consistent key format
                hour_key = start_time.isoformat()
                result["hourly_prices"][hour_key] = price_value

        return result

    def _get_currency(self, raw_data: Dict[str, Any]) -> str:
        """Extract currency from Nordpool response.

        Args:
            raw_data: Raw API response

        Returns:
            Currency code as string
        """
        # Try to get currency from response
        data = raw_data.get("data", {})
        currency = data.get("Currency", Currency.EUR)
        return currency

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from Nordpool.

        Args:
            date_str: Datetime string from API response

        Returns:
            Datetime object or None if parsing fails
        """
        if not date_str:
            return None

        try:
            # Nordpool uses format like "/Date(1625097600000)/" 
            # or sometimes ISO format
            if date_str.startswith("/Date(") and date_str.endswith(")/"):
                # Extract timestamp from /Date(1625097600000)/
                timestamp_ms = int(date_str.replace("/Date(", "").replace(")/", ""))
                return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            else:
                # Try ISO format
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Error parsing datetime '{date_str}': {str(e)}")
            return None

    def _parse_price(self, price_str: Optional[str]) -> Optional[float]:
        """Parse price string from Nordpool.

        Args:
            price_str: Price string from API response

        Returns:
            Float price or None if parsing fails
        """
        if not price_str:
            return None

        try:
            # Nordpool returns prices with currency symbols and possibly commas
            # Replace commas with dots and strip non-numeric characters
            price_str = price_str.replace(',', '.')
            # Extract numeric part, handling cases like "10.45 €/MWh"
            numeric_part = ''.join(c for c in price_str if c.isdigit() or c == '.')
            return float(numeric_part)
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Error parsing price '{price_str}': {str(e)}")
        return None

    def parse_hourly_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices
        """
        hourly_prices = {}

        # Process today's data
        if "today" in data and data["today"]:
            today_data = data["today"]
            if "multiAreaEntries" in today_data:
                for entry in today_data["multiAreaEntries"]:
                    if not isinstance(entry, dict) or "entryPerArea" not in entry:
                        continue
                    if area not in entry["entryPerArea"]:
                        continue
                    start_time = entry.get("deliveryStart")
                    raw_price = entry["entryPerArea"][area]
                    if start_time and raw_price is not None:
                        dt = self._parse_timestamp(start_time)
                        if dt:
                            normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                            hour_key = f"{normalized_hour:02d}:00"
                            price_date = dt.date().isoformat()
                            hourly_prices[hour_key] = {"price": float(raw_price), "api_price_date": price_date}

        return hourly_prices

    def parse_tomorrow_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse tomorrow's hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices
        """
        hourly_prices = {}

        # Process tomorrow's data
        if "tomorrow" in data and data["tomorrow"]:
            tomorrow_data = data["tomorrow"]

            if "multiAreaEntries" in tomorrow_data:
                for entry in tomorrow_data["multiAreaEntries"]:
                    if not isinstance(entry, dict) or "entryPerArea" not in entry:
                        continue

                    if area not in entry["entryPerArea"]:
                        continue

                    # Extract values
                    start_time = entry.get("deliveryStart")
                    raw_price = entry["entryPerArea"][area]

                    if start_time and raw_price is not None:
                        # Parse timestamp
                        dt = self._parse_timestamp(start_time)
                        if dt:
                            # Format as hour key
                            normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                            hour_key = f"{normalized_hour:02d}:00"
                            hourly_prices[hour_key] = float(raw_price)

        return hourly_prices

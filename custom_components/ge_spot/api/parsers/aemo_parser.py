"""Parser for AEMO API responses."""
import logging
import json
import csv
from io import StringIO
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...const.currencies import Currency
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class AemoParser(BasePriceParser):
    """Parser for AEMO API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.AEMO, timezone_service)

    def parse(self, raw_data: Any, area: Optional[str] = None) -> Dict[str, Any]:
        """Parse AEMO price data.

        Returns:
            Parsed data with interval prices, currency, area, and timezone
        """
        
        # Determine timezone based on the area, similar to AemoAPI.get_timezone_for_area
        # Default to "Australia/Sydney" if area is None or not in the specific map
        determined_timezone = "Australia/Sydney"
        if area:
            timezone_map = {
                "NSW1": "Australia/Sydney",
                "QLD1": "Australia/Brisbane",
                "SA1": "Australia/Adelaide",
                "TAS1": "Australia/Hobart",
                "VIC1": "Australia/Melbourne"
            }
            determined_timezone = timezone_map.get(area, "Australia/Sydney")

        result = {
            "interval_raw": {},  # Changed from interval_prices
            "currency": Currency.AUD,
            "area": area,  # Store the area if provided
            "timezone": determined_timezone # Add timezone to the parser's result
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty AEMO data received")
            return result

        # If raw_data is a string (CSV or JSON), parse it
        if isinstance(raw_data, str):
            try:
                # Try JSON format first
                json_data = json.loads(raw_data)
                self._parse_json(json_data, result, area)  # Pass area
            except json.JSONDecodeError:
                # Try CSV format
                try:
                    self._parse_csv(raw_data, result, area)  # Pass area
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse AEMO data as CSV: {e}")
        # If raw_data is a dictionary, extract data directly
        elif isinstance(raw_data, dict):
            # If interval prices were already processed
            if "interval_raw" in raw_data and isinstance(raw_data["interval_raw"], dict):  # Changed from interval_prices
                result["interval_raw"] = raw_data["interval_raw"]  # Changed from interval_prices
            elif "raw_data" in raw_data:
                # Try to parse raw_data entry
                self._parse_json(raw_data, result, area)  # Pass area
            else:
                # Try parsing the dict directly as if it's the JSON response
                self._parse_json(raw_data, result, area)  # Pass area

        # Calculate current and next interval prices if not provided
        if not result.get("current_price"):
            result["current_price"] = self._get_current_price(result["interval_raw"])  # Changed from interval_prices

        if not result.get("next_interval_price"):
            result["next_interval_price"] = self._get_next_interval_price(result["interval_raw"])  # Changed from interval_prices

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from AEMO API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.AUD,  # Default currency for AEMO
            "timezone": "Australia/Sydney",
            "area": "NSW1",  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for area information
            if "area" in data:
                metadata["area"] = data["area"]

            # Check for additional fields
            from ...const.api import Aemo
            if Aemo.SUMMARY_ARRAY in data:
                metadata["data_source"] = "ELEC_NEM_SUMMARY"

                # Look for region information in the first entry
                if data[Aemo.SUMMARY_ARRAY] and isinstance(data[Aemo.SUMMARY_ARRAY], list):
                    first_entry = data[Aemo.SUMMARY_ARRAY][0]
                    if Aemo.REGION_FIELD in first_entry:
                        metadata["area"] = first_entry[Aemo.REGION_FIELD]

        metadata.update({
            "source": self.source,
            "price_count": len(data.get("interval_raw", {})),  # Changed from interval_prices
            "currency": data.get("currency", "AUD"),  # Changed default
            "area": data.get("area", "NSW1"),  # Use area from parsed data
            "has_current_price": "current_price" in data and data["current_price"] is not None,
            "has_next_interval_price": "next_interval_price" in data and data["next_interval_price"] is not None,
            "parser_version": "2.1",  # Updated version
            "parsed_at": datetime.now(timezone.utc).isoformat()
        })

        return metadata

    def _parse_json(self, json_data: Dict[str, Any], result: Dict[str, Any], area: Optional[str] = None) -> None:
        """Parse JSON formatted data from AEMO.

        Args:
            json_data: JSON data
            result: Result dictionary to update
            area: Optional area code to filter results for
        """
        # Check if we're using the consolidated endpoint
        from ...const.api import Aemo
        interval_prices_5min = {}

        if Aemo.SUMMARY_ARRAY in json_data:
            # Process data from the main summary array
            for entry in json_data[Aemo.SUMMARY_ARRAY]:
                # Filter by area if provided
                if area and Aemo.REGION_FIELD in entry and entry[Aemo.REGION_FIELD] != area:
                    continue

                if Aemo.PRICE_FIELD in entry and Aemo.SETTLEMENT_DATE_FIELD in entry:
                    try:
                        # Parse timestamp
                        timestamp_str = entry[Aemo.SETTLEMENT_DATE_FIELD]
                        try:
                            # AEMO timestamps are typically in ISO format with 5-minute intervals
                            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            # Store 5-minute prices as-is for now
                            interval_key = dt.isoformat()
                            # Parse price
                            price = float(entry[Aemo.PRICE_FIELD])
                            interval_prices_5min[interval_key] = price
                        except (ValueError, TypeError):
                            _LOGGER.debug(f"Failed to parse AEMO timestamp: {timestamp_str}")
                    except (KeyError, TypeError):
                        continue

        # Aggregate 5-minute prices to 15-minute intervals
        interval_prices_15min = self._aggregate_to_15min(interval_prices_5min)
        
        # Update result with aggregated 15-minute interval prices
        result["interval_raw"].update(interval_prices_15min)  # Changed from interval_prices

    def _parse_csv(self, csv_data: str, result: Dict[str, Any], area: Optional[str] = None) -> None:
        """Parse CSV formatted data from AEMO.

        Args:
            csv_data: CSV data
            result: Result dictionary to update
            area: Optional area code to filter results for
        """
        interval_prices_5min = {}

        try:
            # Read CSV data
            csv_file = StringIO(csv_data)
            csv_reader = csv.DictReader(csv_file)

            # Parse rows
            for row in csv_reader:
                # Check for required fields
                if "SETTLEMENTDATE" in row and "RRP" in row and "REGIONID" in row:
                    # Filter by area if provided
                    if area and row["REGIONID"] != area:
                        continue
                    try:
                        # Parse timestamp
                        timestamp_str = row["SETTLEMENTDATE"]
                        try:
                            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            # Store 5-minute prices as-is for now
                            interval_key = dt.isoformat()
                            price = float(row["RRP"])
                            interval_prices_5min[interval_key] = price
                        except (ValueError, TypeError):
                            _LOGGER.debug(f"Failed to parse AEMO CSV timestamp: {timestamp_str}")
                    except (KeyError, TypeError):
                        continue
        except Exception as e:
            _LOGGER.warning(f"Error parsing AEMO CSV data: {e}")

        # Aggregate 5-minute prices to 15-minute intervals
        interval_prices_15min = self._aggregate_to_15min(interval_prices_5min)
        
        # Update result with aggregated 15-minute interval prices
        result["interval_raw"].update(interval_prices_15min)  # Changed from interval_prices

    def _aggregate_to_15min(self, prices_5min: Dict[str, float]) -> Dict[str, float]:
        """Aggregate 5-minute prices to 15-minute intervals.
        
        AEMO provides 5-minute dispatch prices, but we aggregate them to 15-minute intervals
        to match our target resolution. Each 15-minute interval is the average of 3x 5-minute prices.
        
        Args:
            prices_5min: Dictionary of 5-minute interval prices with ISO timestamp keys
            
        Returns:
            Dictionary of 15-minute interval prices (averaged from 5-min data)
        """
        from collections import defaultdict
        
        interval_15min_prices = defaultdict(list)
        
        for interval_key, price in prices_5min.items():
            try:
                # Parse the timestamp
                dt = datetime.fromisoformat(interval_key)
                # Round down to nearest 15-minute interval: 00, 15, 30, 45
                minute_rounded = (dt.minute // 15) * 15
                interval_dt = dt.replace(minute=minute_rounded, second=0, microsecond=0)
                interval_key_15min = interval_dt.isoformat()
                # Add to the 15-minute interval bucket
                interval_15min_prices[interval_key_15min].append(price)
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Failed to parse timestamp for aggregation: {interval_key}, error: {e}")
                continue
        
        # Calculate average for each 15-minute interval
        result = {}
        for interval_key_15min, prices in interval_15min_prices.items():
            if prices:
                # Average of all 5-minute prices within the 15-minute interval (typically 3 values)
                avg_price = sum(prices) / len(prices)
                result[interval_key_15min] = avg_price
                _LOGGER.debug(f"Aggregated {len(prices)} 5-min prices to 15-min interval {interval_key_15min}: {avg_price:.2f}")
        
        return result

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from AEMO format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Try ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # Try common AEMO formats
            formats = [
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%d-%m-%Y %H:%M:%S",
                "%Y%m%d%H%M%S"
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except (ValueError, TypeError):
                    continue

            _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
            return None

    def _get_current_price(self, interval_prices: Dict[str, float]) -> Optional[float]:
        """Get current interval price.

        Args:
            interval_prices: Dictionary of interval prices

        Returns:
            Current interval price or None if not available
        """
        if not interval_prices:
            return None

        now = datetime.now()

        # Round down to nearest 15-minute interval
        minute_rounded = (now.minute // 15) * 15
        current_interval = now.replace(minute=minute_rounded, second=0, microsecond=0)
        current_interval_key = current_interval.isoformat()

        _LOGGER.debug(f"Looking for current interval price with key: {current_interval_key}")
        
        return interval_prices.get(current_interval_key)

    def _get_next_interval_price(self, interval_prices: Dict[str, float]) -> Optional[float]:
        """Get next interval price.

        Args:
            interval_prices: Dictionary of interval prices

        Returns:
            Next interval price or None if not available
        """
        if not interval_prices:
            return None

        now = datetime.now()
        
        # Round down to current 15-minute interval, then add 15 minutes
        minute_rounded = (now.minute // 15) * 15
        current_interval = now.replace(minute=minute_rounded, second=0, microsecond=0)
        next_interval = current_interval + timedelta(minutes=15)
        next_interval_key = next_interval.isoformat()

        _LOGGER.debug(f"Looking for next interval price with key: {next_interval_key}")

        return interval_prices.get(next_interval_key)

    def _calculate_day_average(self, interval_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            interval_prices: Dictionary of interval prices

        Returns:
            Day average price or None if not enough data
        """
        if not interval_prices:
            return None

        # Get today's date
        today = datetime.now().date()

        # Filter prices for today
        today_prices = []
        for interval_key, price in interval_prices.items():
            try:
                hour_dt = datetime.fromisoformat(interval_key)
                if hour_dt.date() == today:
                    today_prices.append(price)
            except (ValueError, TypeError):
                continue

        # Calculate average if we have enough prices
        if len(today_prices) >= 12:
            return sum(today_prices) / len(today_prices)

        return None

"""Parser for AEMO API responses."""
import logging
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class AemoParser(BasePriceParser):
    """Parser for AEMO API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.AEMO)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AEMO API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "hourly_prices": {},
            "currency": data.get("currency", "AUD"),
            "source": self.source
        }

        # If hourly prices were already processed
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]
        elif "raw_data" in data and isinstance(data["raw_data"], str):
            # Try to parse raw data
            try:
                # Try JSON format
                json_data = json.loads(data["raw_data"])
                self._parse_json(json_data, result)
            except json.JSONDecodeError:
                # Try CSV format
                try:
                    self._parse_csv(data["raw_data"], result)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse AEMO CSV: {e}")

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
        """Extract metadata from AEMO API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "AUD",  # Default currency for AEMO
            "data_sources": []
        }

        # Check if we're using the consolidated endpoint
        if isinstance(data, dict):
            # Check if this is the new consolidated format
            from ...const.api import Aemo

            if Aemo.SUMMARY_ARRAY in data:
                metadata["data_sources"].append("current")

                # Add price details
                price_details = {
                    "current": {
                        "source": Aemo.SUMMARY_ARRAY
                    }
                }

                # Add price details for the prices array if available
                if Aemo.PRICES_ARRAY in data:
                    price_details["prices"] = {
                        "source": Aemo.PRICES_ARRAY
                    }

                metadata["price_details"] = price_details

            # Legacy format handling (for backward compatibility)
            else:
                # Check which data sources are available in legacy format
                if "current" in data and data["current"]:
                    metadata["data_sources"].append("current")

                if "historical" in data and data["historical"]:
                    metadata["data_sources"].append("historical")

                if "forecast" in data and data["forecast"]:
                    metadata["data_sources"].append("forecast")

                # Add price details if available
                price_details = {}

                # Try to extract price details from current data
                if "current" in data and data["current"] and isinstance(data["current"], str):
                    try:
                        current_json = json.loads(data["current"])
                        if "ELEC_NEM_SUMMARY" in current_json:
                            price_details["current"] = {
                                "timestamp": current_json.get("timestamp"),
                                "source": "ELEC_NEM_SUMMARY"
                            }
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

                # Try to extract price details from historical data
                if "historical" in data and data["historical"] and isinstance(data["historical"], str):
                    try:
                        price_details["historical"] = {
                            "source": "DAILY_PRICE"
                        }
                    except (TypeError, KeyError):
                        pass

                # Try to extract price details from forecast data
                if "forecast" in data and data["forecast"] and isinstance(data["forecast"], str):
                    try:
                        forecast_json = json.loads(data["forecast"])
                        if "PREDISPATCH_PRICE" in forecast_json:
                            price_details["forecast"] = {
                                "timestamp": forecast_json.get("timestamp"),
                                "source": "PREDISPATCH_PRICE"
                            }
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

                if price_details:
                    metadata["price_details"] = price_details

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from AEMO API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

        # If data is a dictionary
        if isinstance(data, dict):
            # Check if this is the new consolidated format
            from ...const.api import Aemo

            if Aemo.SUMMARY_ARRAY in data:
                # Process data from the main summary array
                for entry in data[Aemo.SUMMARY_ARRAY]:
                    if entry.get(Aemo.REGION_FIELD) == area:
                        if Aemo.PRICE_FIELD in entry and Aemo.SETTLEMENT_DATE_FIELD in entry:
                            try:
                                # Parse timestamp
                                timestamp = self._parse_timestamp(entry[Aemo.SETTLEMENT_DATE_FIELD])
                                if timestamp:
                                    # AEMO provides 5-minute intervals
                                    # We need to map to the standard hour format for consistency
                                    normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                                    hour_key = f"{normalized_hour:02d}:00"

                                    # Parse price
                                    price = float(entry[Aemo.PRICE_FIELD])

                                    # Store with full timestamp as key for granular data
                                    minute_key = f"{timestamp.hour:02d}:{timestamp.minute:02d}"
                                    _LOGGER.debug(f"AEMO data point at {minute_key} with price {price}")

                                    # Add to hourly prices - intentionally overwrite as we want the latest price for each hour
                                    hourly_prices[hour_key] = price
                            except (ValueError, TypeError) as e:
                                _LOGGER.warning(f"Failed to parse AEMO price: {e}")

                # Additionally check PRICES array for backup
                if Aemo.PRICES_ARRAY in data:
                    for entry in data[Aemo.PRICES_ARRAY]:
                        if entry.get(Aemo.REGION_FIELD) == area and Aemo.RRP_FIELD in entry:
                            # Use this price as a backup if we don't have the current hour
                            # This won't have a timestamp, so we'll use the current hour
                            now = datetime.now()
                            normalized_hour, adjusted_date = normalize_hour_value(now.hour, now.date())
                            hour_key = f"{normalized_hour:02d}:00"

                            # Only add if we don't already have a price for this hour
                            if hour_key not in hourly_prices:
                                try:
                                    price = float(entry[Aemo.RRP_FIELD])
                                    hourly_prices[hour_key] = price
                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning(f"Failed to parse AEMO RRP price: {e}")

            # Legacy format handling - if not using consolidated endpoint
            else:
                # Process current data
                if "current" in data and data["current"] and isinstance(data["current"], str):
                    try:
                        current_json = json.loads(data["current"])
                        self._extract_current_prices(current_json, area, hourly_prices)
                    except (json.JSONDecodeError, TypeError):
                        _LOGGER.warning("Failed to parse current AEMO data as JSON")

                # Process historical data
                if "historical" in data and data["historical"] and isinstance(data["historical"], str):
                    try:
                        # Try as JSON first
                        try:
                            historical_json = json.loads(data["historical"])
                            self._extract_historical_prices(historical_json, area, hourly_prices)
                        except json.JSONDecodeError:
                            # Try as CSV
                            self._extract_historical_prices_csv(data["historical"], area, hourly_prices)
                    except Exception as e:
                        _LOGGER.warning(f"Failed to parse historical AEMO data: {e}")

                # Process forecast data
                if "forecast" in data and data["forecast"] and isinstance(data["forecast"], str):
                    try:
                        forecast_json = json.loads(data["forecast"])
                        self._extract_forecast_prices(forecast_json, area, hourly_prices)
                    except (json.JSONDecodeError, TypeError):
                        _LOGGER.warning("Failed to parse forecast AEMO data as JSON")

        return hourly_prices

    def _extract_current_prices(self, data: Dict[str, Any], area: str, hourly_prices: Dict[str, float]) -> None:
        """Extract current prices from AEMO ELEC_NEM_SUMMARY data.

        Args:
            data: JSON data
            area: Area code
            hourly_prices: Dictionary to update with hourly prices
        """
        # Check if we have ELEC_NEM_SUMMARY data
        if "ELEC_NEM_SUMMARY" not in data:
            return

        # Get the data array
        summary_data = data["ELEC_NEM_SUMMARY"]
        if not isinstance(summary_data, list):
            return

        # Find the entry for the specified area
        for entry in summary_data:
            if "REGIONID" in entry and entry["REGIONID"] == area:
                if "PRICE" in entry and "SETTLEMENTDATE" in entry:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(entry["SETTLEMENTDATE"])
                        if timestamp:
                            # Format as hour string (HH:00)
                            hour_key = f"{timestamp.hour:02d}:00"

                            # Parse price
                            price = float(entry["PRICE"])

                            # Add to hourly prices
                            hourly_prices[hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse AEMO current price: {e}")

    def _extract_historical_prices(self, data: Dict[str, Any], area: str, hourly_prices: Dict[str, float]) -> None:
        """Extract historical prices from AEMO DAILY_PRICE data.

        Args:
            data: JSON data
            area: Area code
            hourly_prices: Dictionary to update with hourly prices
        """
        # Check if we have data array
        if not isinstance(data, dict) or "data" not in data or not isinstance(data["data"], list):
            return

        # Process data entries
        for entry in data["data"]:
            if "REGIONID" in entry and entry["REGIONID"] == area:
                if "RRP" in entry and "SETTLEMENTDATE" in entry:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(entry["SETTLEMENTDATE"])
                        if timestamp:
                            # Format as hour string (HH:00)
                            hour_key = f"{timestamp.hour:02d}:00"

                            # Parse price
                            price = float(entry["RRP"])

                            # Add to hourly prices if not already present
                            if hour_key not in hourly_prices:
                                hourly_prices[hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse AEMO historical price: {e}")

    def _extract_historical_prices_csv(self, csv_data: str, area: str, hourly_prices: Dict[str, float]) -> None:
        """Extract historical prices from AEMO DAILY_PRICE CSV data.

        Args:
            csv_data: CSV data
            area: Area code
            hourly_prices: Dictionary to update with hourly prices
        """
        # Try to parse CSV
        csv_reader = csv.DictReader(StringIO(csv_data))

        # Look for common field names
        region_fields = ["REGIONID", "REGION"]
        timestamp_fields = ["SETTLEMENTDATE", "INTERVAL_DATETIME", "Time", "Timestamp"]
        price_fields = ["RRP", "PRICE", "Price", "Value"]

        for row in csv_reader:
            # Find region field
            region_field = next((f for f in region_fields if f in row), None)
            if not region_field or row[region_field] != area:
                continue

            # Find timestamp field
            timestamp_field = next((f for f in timestamp_fields if f in row), None)
            if not timestamp_field:
                continue

            # Find price field
            price_field = next((f for f in price_fields if f in row), None)
            if not price_field:
                continue

            try:
                # Parse timestamp
                timestamp = self._parse_timestamp(row[timestamp_field])
                if timestamp:
                    # Format as hour string (HH:00)
                    hour_key = f"{timestamp.hour:02d}:00"

                    # Parse price
                    price = float(row[price_field])

                    # Add to hourly prices if not already present
                    if hour_key not in hourly_prices:
                        hourly_prices[hour_key] = price
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Failed to parse AEMO historical CSV row: {e}")

    def _extract_forecast_prices(self, data: Dict[str, Any], area: str, hourly_prices: Dict[str, float]) -> None:
        """Extract forecast prices from AEMO PREDISPATCH_PRICE data.

        Args:
            data: JSON data
            area: Area code
            hourly_prices: Dictionary to update with hourly prices
        """
        # Check if we have PREDISPATCH_PRICE data
        if "PREDISPATCH_PRICE" not in data:
            return

        # Get the data array
        forecast_data = data["PREDISPATCH_PRICE"]
        if not isinstance(forecast_data, list):
            return

        # Process forecast entries
        for entry in forecast_data:
            if "REGIONID" in entry and entry["REGIONID"] == area:
                if "RRP" in entry and "DATETIME" in entry:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(entry["DATETIME"])
                        if timestamp:
                            # Format as hour string (HH:00)
                            hour_key = f"{timestamp.hour:02d}:00"

                            # Parse price
                            price = float(entry["RRP"])

                            # Add to hourly prices if not already present
                            if hour_key not in hourly_prices:
                                hourly_prices[hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse AEMO forecast price: {e}")

    def _parse_json(self, json_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Parse AEMO JSON response.

        Args:
            json_data: JSON data
            result: Result dictionary to update
        """
        # AEMO API can return data in different formats
        # Try to handle common formats

        # Format 1: Data in "data" field with "SETTLEMENTDATE" and "RRP" fields
        if "data" in json_data and isinstance(json_data["data"], list):
            for item in json_data["data"]:
                if "SETTLEMENTDATE" in item and "RRP" in item:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(item["SETTLEMENTDATE"])
                        if timestamp:
                            # Format as ISO string for the hour
                            hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                            # Parse price
                            price = float(item["RRP"])

                            # Add to hourly prices
                            result["hourly_prices"][hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse AEMO data item: {e}")

        # Format 2: Data in "price_data" field with "timestamp" and "price" fields
        elif "price_data" in json_data and isinstance(json_data["price_data"], list):
            for item in json_data["price_data"]:
                if "timestamp" in item and "price" in item:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(item["timestamp"])
                        if timestamp:
                            # Format as ISO string for the hour
                            hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                            # Parse price
                            price = float(item["price"])

                            # Add to hourly prices
                            result["hourly_prices"][hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse AEMO price data item: {e}")

    def _parse_csv(self, csv_data: str, result: Dict[str, Any]) -> None:
        """Parse AEMO CSV response.

        Args:
            csv_data: CSV data
            result: Result dictionary to update
        """
        # Try to parse CSV
        csv_reader = csv.DictReader(StringIO(csv_data))

        # Look for common field names
        timestamp_fields = ["SETTLEMENTDATE", "INTERVAL_DATETIME", "Time", "Timestamp"]
        price_fields = ["RRP", "PRICE", "Price", "Value"]

        for row in csv_reader:
            # Find timestamp field
            timestamp_field = next((f for f in timestamp_fields if f in row), None)
            if not timestamp_field:
                continue

            # Find price field
            price_field = next((f for f in price_fields if f in row), None)
            if not price_field:
                continue

            try:
                # Parse timestamp
                timestamp = self._parse_timestamp(row[timestamp_field])
                if timestamp:
                    # Format as ISO string for the hour
                    hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                    # Parse price
                    price = float(row[price_field])

                    # Add to hourly prices
                    result["hourly_prices"][hour_key] = price
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Failed to parse AEMO CSV row: {e}")

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

        # Try both formats - full ISO and simple HH:00
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_hour_key_full = current_hour.strftime("%Y-%m-%dT%H:00:00")
        current_hour_key_simple = f"{now.hour:02d}:00"

        _LOGGER.debug(f"Looking for current hour price with keys: {current_hour_key_simple} or {current_hour_key_full}")

        # Try simple format first (which is what we're storing in our parser updates)
        if current_hour_key_simple in hourly_prices:
            return hourly_prices[current_hour_key_simple]

        # Fall back to full format (legacy)
        return hourly_prices.get(current_hour_key_full)

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
        next_hour = (now.hour + 1) % 24

        # Try both formats - full ISO and simple HH:00
        next_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        next_hour_key_full = next_dt.strftime("%Y-%m-%dT%H:00:00")
        next_hour_key_simple = f"{next_hour:02d}:00"

        _LOGGER.debug(f"Looking for next hour price with keys: {next_hour_key_simple} or {next_hour_key_full}")

        # Try simple format first (which is what we're storing in our parser updates)
        if next_hour_key_simple in hourly_prices:
            return hourly_prices[next_hour_key_simple]

        # Fall back to full format (legacy)
        return hourly_prices.get(next_hour_key_full)

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

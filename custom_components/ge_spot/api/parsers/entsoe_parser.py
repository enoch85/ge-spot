"""Parser for ENTSO-E API responses."""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone, time
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EntsoeParser(BasePriceParser):
    """Parser for ENTSO-E API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.ENTSOE, timezone_service)
        _LOGGER.debug("Initialized ENTSO-E parser with standardized timestamp handling")

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse ENTSO-E API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "today_hourly_prices": {},
            "currency": data.get("currency", "EUR"),
            "source": self.source
        }

        # If hourly prices were already processed - convert to today_hourly_prices
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["today_hourly_prices"] = data["hourly_prices"]
        # Support for new format if it exists
        elif "today_hourly_prices" in data and isinstance(data["today_hourly_prices"], dict):
            result["today_hourly_prices"] = data["today_hourly_prices"]

            # Add current and next hour prices if available
            if "current_price" in data:
                result["current_price"] = data["current_price"]

            if "next_hour_price" in data:
                result["next_hour_price"] = data["next_hour_price"]

            # Calculate current and next hour prices if not provided
            if "current_price" not in result:
                result["current_price"] = self._get_current_price(result["today_hourly_prices"])

            if "next_hour_price" not in result:
                result["next_hour_price"] = self._get_next_hour_price(result["today_hourly_prices"])

            # Calculate day average if enough prices
            if len(result["today_hourly_prices"]) >= 12:
                result["day_average_price"] = self._calculate_day_average(result["today_hourly_prices"])

            return result

        # Parse XML response
        if "raw_data" in data and isinstance(data["raw_data"], str):
            try:
                return self._parse_xml(data["raw_data"])
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E XML: {e}")

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from ENTSO-E API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "EUR",  # Default currency for ENTSO-E
        }

        # If data is a string (XML), try to parse it
        if isinstance(data, str):
            try:
                # Parse XML
                root = ET.fromstring(data)

                # ENTSO-E uses a specific namespace
                ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

                # Find time series elements
                time_series = root.findall(".//ns:TimeSeries", ns)

                for ts in time_series:
                    # Check if this is a day-ahead price time series
                    business_type = ts.find(".//ns:businessType", ns)
                    if business_type is None or business_type.text != "A62":
                        # If not A62 (Day-ahead allocation), try A44 (Day-ahead)
                        if business_type is None or business_type.text != "A44":
                            # If neither A62 nor A44, skip this time series
                            continue

                    # Get currency
                    currency = ts.find(".//ns:currency_Unit.name", ns)
                    if currency is not None:
                        metadata["currency"] = currency.text
                        break

            except Exception as e:
                _LOGGER.error(f"Failed to extract metadata from ENTSO-E XML: {e}")

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from ENTSO-E API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
            or a dictionary with both 'today_hourly_prices' and 'tomorrow_hourly_prices'
        """
        today_hourly_prices = {}
        tomorrow_hourly_prices = {}

        # If data is a string (XML), try to parse it
        if isinstance(data, str):
            try:
                # Parse XML
                root = ET.fromstring(data)

                # ENTSO-E uses a specific namespace
                ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

                # Find time series elements
                time_series = root.findall(".//ns:TimeSeries", ns)

                for ts in time_series:
                    # Check if this is a day-ahead price time series
                    business_type = ts.find(".//ns:businessType", ns)
                    if business_type is None or business_type.text != "A62":
                        # If not A62 (Day-ahead allocation), try A44 (Day-ahead)
                        if business_type is None or business_type.text != "A44":
                            # If neither A62 nor A44, skip this time series
                            continue

                    # Get period start time
                    period = ts.find(".//ns:Period", ns)
                    if period is None:
                        continue

                    start_str = period.find(".//ns:timeInterval/ns:start", ns)
                    if start_str is None:
                        continue

                    try:
                        # Parse start time
                        start_time = datetime.fromisoformat(start_str.text.replace('Z', '+00:00'))

                        # Get price points
                        points = ts.findall(".//ns:Point", ns)

                        # Parse points
                        for point in points:
                            position = point.find("ns:position", ns)
                            price = point.find("ns:price.amount", ns)

                            if position is not None and price is not None:
                                try:
                                    pos = int(position.text)
                                    price_val = float(price.text)

                                    # Calculate hour
                                    hour_time = start_time + timedelta(hours=pos-1)

                                    # Use the utility function to normalize the hour value if needed
                                    try:
                                        # Use relative import to avoid module not found error
                                        from ...timezone.timezone_utils import normalize_hour_value, format_hour_key
                                        normalized_hour, adjusted_date = normalize_hour_value(hour_time.hour, hour_time.date())
                                        
                                        # Create normalized datetime
                                        from datetime import time
                                        normalized_time = datetime.combine(adjusted_date, time(hour=normalized_hour))
                                        normalized_time = normalized_time.replace(tzinfo=hour_time.tzinfo)
                                        
                                        # Format as ISO string for consistent date handling
                                        hour_key = super().format_timestamp_to_iso(normalized_time)
                                        
                                        # Check if this timestamp belongs to tomorrow using date comparison
                                        # to ensure DST changes don't affect our classification
                                        dt_date = normalized_time.date()
                                        tomorrow_date = self.tomorrow
                                        is_tomorrow = dt_date == tomorrow_date
                                        
                                        # For ENTSOE, we could also look at position - higher positions are likely tomorrow
                                        if not is_tomorrow and pos > 20:
                                            # If position is high, it's likely tomorrow data
                                            _LOGGER.debug(f"High position ({pos}) suggests tomorrow data")
                                            is_tomorrow = True
                                        
                                        if is_tomorrow:
                                            tomorrow_hourly_prices[hour_key] = price_val
                                            _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {price_val} (pos: {pos})")
                                        else:
                                            today_hourly_prices[hour_key] = price_val
                                            _LOGGER.debug(f"Added TODAY price with ISO timestamp: {hour_key} = {price_val} (pos: {pos})")
                                            
                                    except ValueError as e:
                                        # Skip invalid hours
                                        _LOGGER.warning(f"Skipping invalid hour value in ENTSOE data: {hour_time.hour}:00 - {e}")
                                        continue
                                    except ImportError as e:
                                        _LOGGER.warning(f"Import error for timezone utils: {e}, using original hour")
                                        # Format as ISO string for consistent date handling
                                        hour_key = hour_time.strftime("%Y-%m-%dT%H:00:00")
                                        
                                        # Check if this timestamp belongs to tomorrow
                                        if hour_time.date() == self.tomorrow:
                                            tomorrow_hourly_prices[hour_key] = price_val
                                            _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {price_val}")
                                        else:
                                            today_hourly_prices[hour_key] = price_val
                                            _LOGGER.debug(f"Added TODAY price with ISO timestamp: {hour_key} = {price_val}")
                                            
                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning(f"Failed to parse point: {e}")

                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse start time: {e}")

            except Exception as e:
                _LOGGER.error(f"Failed to parse hourly prices from ENTSO-E XML: {e}")

        # If we found tomorrow's prices, return both sets
        if tomorrow_hourly_prices:
            result = {
                "today_hourly_prices": today_hourly_prices,
                "tomorrow_hourly_prices": tomorrow_hourly_prices
            }
            _LOGGER.info(f"Extracted {len(tomorrow_hourly_prices)} tomorrow prices from ENTSOE data")
            return result
        
        return today_hourly_prices

    def _select_best_time_series(self, all_series):
        """Select the best TimeSeries to use for price data.

        Args:
            all_series: List of dictionaries with metadata and prices

        Returns:
            The best TimeSeries or None if no valid series found
        """
        if not all_series:
            return None

        # If only one series, use it
        if len(all_series) == 1:
            return all_series[0]

        # Get current date in UTC
        today = datetime.now(timezone.utc).date()

        # Filter series that contain today's data
        today_series = []
        for series in all_series:
            # Extract hour keys
            hour_keys = list(series["prices"].keys())
            if not hour_keys:
                continue

            # Try to find a price entry for today
            for hour_key in hour_keys:
                try:
                    hour_dt = datetime.fromisoformat(hour_key)
                    if hour_dt.date() == today:
                        today_series.append(series)
                        break
                except (ValueError, TypeError):
                    continue

        # If we found series containing today's data, use those
        if today_series:
            _LOGGER.debug(f"Found {len(today_series)} TimeSeries containing today's data")

            # If only one series contains today's data, use it
            if len(today_series) == 1:
                _LOGGER.debug("Using the only TimeSeries that contains today's data")
                return today_series[0]

            # If multiple series contain today's data, use business type criteria
            for series in today_series:
                if series["metadata"]["business_type"] == "A62":
                    _LOGGER.debug("Selected TimeSeries with business_type A62 containing today's data")
                    return series

            for series in today_series:
                if series["metadata"]["business_type"] == "A44":
                    _LOGGER.debug("Selected TimeSeries with business_type A44 containing today's data")
                    return series

            # Fall back to first series containing today's data
            _LOGGER.debug("Falling back to first TimeSeries containing today's data")
            return today_series[0]

        _LOGGER.debug("No TimeSeries contains today's data, falling back to business type criteria")

        # If no series contains today's data, fall back to business type criteria
        # First try to identify by businessType
        # A62 (Day-ahead allocation) is the correct spot price data
        for series in all_series:
            if series["metadata"]["business_type"] == "A62":
                return series

        # Next, try A44 (Day-ahead)
        for series in all_series:
            if series["metadata"]["business_type"] == "A44":
                return series

        # Fallback: try a heuristic approach
        # Use overnight prices as a heuristic (should be lower)
        overnight_averages = []
        for series in all_series:
            overnight_prices = []
            for hour_str, price in series["prices"].items():
                try:
                    hour_dt = datetime.fromisoformat(hour_str)
                    hour = hour_dt.hour
                    if 0 <= hour <= 6:  # Overnight hours
                        overnight_prices.append(price)
                except (ValueError, TypeError):
                    # Try simple hour format
                    try:
                        hour = int(hour_str.split(":")[0])
                        if 0 <= hour <= 6:  # Overnight hours
                            overnight_prices.append(price)
                    except (ValueError, TypeError, IndexError):
                        continue

            if overnight_prices:
                avg = sum(overnight_prices) / len(overnight_prices)
                overnight_averages.append({
                    "series": series,
                    "overnight_avg": avg
                })

        # Choose the series with the lowest overnight average
        if overnight_averages:
            overnight_averages.sort(key=lambda x: x["overnight_avg"])
            return overnight_averages[0]["series"]

        # If all else fails, use the first series
        return all_series[0]

    def _parse_xml(self, xml_data: str) -> Dict[str, Any]:
        """Parse ENTSO-E XML response.

        Args:
            xml_data: XML response data

        Returns:
            Parsed data with hourly prices
        """
        result = {
            "today_hourly_prices": {},
            "currency": "EUR",
            "source": self.source
        }

        try:
            # Parse XML
            root = ET.fromstring(xml_data)

            # ENTSO-E uses a specific namespace
            ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

            # Find time series elements
            time_series = root.findall(".//ns:TimeSeries", ns)

            # Store data from all TimeSeries to compare
            all_hourly_prices = []

            # Process each TimeSeries to find the best one
            for ts_index, ts in enumerate(time_series):
                # Extract metadata
                business_type_elem = ts.find(".//ns:businessType", ns)
                business_type = business_type_elem.text if business_type_elem is not None else "unknown"

                curve_type_elem = ts.find(".//ns:curveType", ns)
                curve_type = curve_type_elem.text if curve_type_elem is not None else "unknown"

                currency_elem = ts.find(".//ns:currency_Unit.name", ns)
                entsoe_currency = currency_elem.text if currency_elem is not None else "EUR"

                unit_name_elem = ts.find(".//ns:price_Measure_Unit.name", ns)
                unit_name = unit_name_elem.text if unit_name_elem is not None else "unknown"

                # Process periods in this time series
                raw_hourly_prices = {}
                metadata = {
                    "business_type": business_type,
                    "curve_type": curve_type,
                    "currency": entsoe_currency,
                    "unit": unit_name,
                    "index": ts_index
                }

                # Get period start time
                period = ts.find(".//ns:Period", ns)
                if period is None:
                    continue

                start_str = period.find(".//ns:timeInterval/ns:start", ns)
                if start_str is None:
                    continue

                try:
                    # Parse start time
                    start_time = datetime.fromisoformat(start_str.text.replace('Z', '+00:00'))

                    # Get price points
                    points = ts.findall(".//ns:Point", ns)

                    # Parse points
                    for point in points:
                        position = point.find("ns:position", ns)
                        price = point.find("ns:price.amount", ns)

                        if position is not None and price is not None:
                            try:
                                pos = int(position.text)
                                price_val = float(price.text)

                                # Calculate hour
                                hour_time = start_time + timedelta(hours=pos-1)

                                # Use the utility function to normalize the hour value if needed
                                try:
                                    # Use relative import to avoid module not found error
                                    from ...timezone.timezone_utils import normalize_hour_value, format_hour_key
                                    normalized_hour, adjusted_date = normalize_hour_value(hour_time.hour, hour_time.date())

                                    # Create normalized datetime
                                    from datetime import time
                                    normalized_time = datetime.combine(adjusted_date, time(hour=normalized_hour))
                                    normalized_time = normalized_time.replace(tzinfo=hour_time.tzinfo)

                                    # Format as ISO string using standardized method
                                    hour_key = super().format_timestamp_to_iso(normalized_time)

                                    # Add to hourly prices
                                    raw_hourly_prices[hour_key] = price_val
                                    
                                    # Add debug info about tomorrow's data
                                    if super().is_tomorrow_timestamp(normalized_time):
                                        _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {price_val}")
                                except ValueError as e:
                                    # Skip invalid hours
                                    _LOGGER.warning(f"Skipping invalid hour value in ENTSOE data: {hour_time.hour}:00 - {e}")
                                    continue
                                except ImportError as e:
                                    _LOGGER.warning(f"Import error for timezone utils: {e}, using original hour")
                                    hour_key = hour_time.strftime("%Y-%m-%dT%H:00:00")
                                    raw_hourly_prices[hour_key] = price_val
                            except (ValueError, TypeError) as e:
                                _LOGGER.warning(f"Failed to parse point: {e}")

                    # Store this TimeSeries prices for comparison
                    if raw_hourly_prices:
                        all_hourly_prices.append({
                            "metadata": metadata,
                            "prices": raw_hourly_prices
                        })

                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to parse start time: {e}")

            # Select the best TimeSeries
            selected_series = self._select_best_time_series(all_hourly_prices)
            if not selected_series:
                _LOGGER.error("Failed to identify any valid price TimeSeries")
                return result

            # Process the selected series
            result["today_hourly_prices"] = selected_series["prices"]
            result["currency"] = selected_series["metadata"]["currency"]
            
            # Remove the legacy format since we're using today_hourly_prices
            if "hourly_prices" in result:
                del result["hourly_prices"]

        except Exception as e:
            _LOGGER.error(f"Failed to parse ENTSO-E XML: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["today_hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["today_hourly_prices"])

        # Calculate day average if enough prices
        if len(result["today_hourly_prices"]) >= 12:
            result["day_average_price"] = self._calculate_day_average(result["today_hourly_prices"])

        return result

    def _get_current_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get current hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Current hour price or None if not available
        """
        if not hourly_prices:
            return None

        # Use timezone-aware datetime
        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Use the standardized method for timestamp formatting
        current_hour_key = super().format_timestamp_to_iso(current_hour)
        
        if current_hour_key in hourly_prices:
            return hourly_prices.get(current_hour_key)
            
        # Try alternative formats as fallback
        # This helps with backward compatibility but maintains standardized approach
        try:
            from ...timezone.timezone_utils import format_hour_key
            alt_hour_key = format_hour_key(current_hour)
            if alt_hour_key != current_hour_key and alt_hour_key in hourly_prices:
                _LOGGER.debug(f"Found current hour price using alternative key format: {alt_hour_key}")
                return hourly_prices.get(alt_hour_key)
        except ImportError:
            pass
            
        # Simple format as last resort
        simple_key = f"{current_hour.hour:02d}:00"
        if simple_key in hourly_prices:
            _LOGGER.debug(f"Found current hour price using simple key format: {simple_key}")
            return hourly_prices.get(simple_key)

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

        now = datetime.now(timezone.utc)
        next_hour = (now.replace(minute=0, second=0, microsecond=0) +
                    timedelta(hours=1))
        
        # Use the standardized method for timestamp formatting
        next_hour_key = super().format_timestamp_to_iso(next_hour)
        
        if next_hour_key in hourly_prices:
            return hourly_prices.get(next_hour_key)
            
        # Try alternative formats as fallback
        # This helps with backward compatibility but maintains standardized approach
        try:
            from ...timezone.timezone_utils import format_hour_key
            alt_hour_key = format_hour_key(next_hour)
            if alt_hour_key != next_hour_key and alt_hour_key in hourly_prices:
                _LOGGER.debug(f"Found next hour price using alternative key format: {alt_hour_key}")
                return hourly_prices.get(alt_hour_key)
        except ImportError:
            pass
            
        # Simple format as last resort
        simple_key = f"{next_hour.hour:02d}:00"
        if simple_key in hourly_prices:
            _LOGGER.debug(f"Found next hour price using simple key format: {simple_key}")
            return hourly_prices.get(simple_key)

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

        # Get today's date
        today = datetime.now(timezone.utc).date()

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

"""Parser for ENTSO-E API responses."""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone, time
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser
from ...timezone.timezone_utils import normalize_hour_value

_LOGGER = logging.getLogger(__name__)

class EntsoeParser(BasePriceParser):
    """Parser for ENTSO-E API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.ENTSOE, timezone_service)

    def parse(self, data: Any) -> Dict[str, Any]:
        """Parse ENTSO-E API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        result = {
            "hourly_prices": {},
            "currency": "EUR",
            "source": self.source
        }

        # Parse XML response
        if isinstance(data, str) and "<Publication_MarketDocument" in data:
            try:
                result = self._parse_xml(data)
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E XML: {e}")
                return result
        
        # If data is a dictionary with "raw_data" key containing XML
        elif isinstance(data, dict) and "raw_data" in data and isinstance(data["raw_data"], str):
            try:
                if "<Publication_MarketDocument" in data["raw_data"]:
                    result = self._parse_xml(data["raw_data"])
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E XML from raw_data: {e}")
                return result

        # If data is a dictionary with multiple XML responses
        elif isinstance(data, dict) and "xml_responses" in data and isinstance(data["xml_responses"], list):
            hourly_prices = {}
            for xml_response in data["xml_responses"]:
                try:
                    parsed = self._parse_xml(xml_response)
                    if parsed and "hourly_prices" in parsed:
                        hourly_prices.update(parsed["hourly_prices"])
                except Exception as e:
                    _LOGGER.error(f"Failed to parse XML response from list: {e}")
            
            if hourly_prices:
                result["hourly_prices"] = hourly_prices

        # If hourly prices were already processed
        elif isinstance(data, dict) and "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]
            
            # Set currency if available
            if "currency" in data:
                result["currency"] = data["currency"]

        # Add current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])
        
        # Add metadata
        result["metadata"] = self.extract_metadata(result)
        
        # Validate the data
        if not self.validate_parsed_data(result):
            _LOGGER.warning(f"ENTSOE data validation failed")

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from ENTSO-E API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "source": self.source,
            "currency": "EUR",  # Default currency for ENTSO-E
            "timezone": "Europe/Brussels",  # Default timezone for ENTSO-E
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
                
                price_count = 0

                for ts in time_series:
                    # Check if this is a day-ahead price time series
                    business_type = ts.find(".//ns:businessType", ns)
                    if business_type is None or business_type.text != "A62":
                        # If not A62 (Day-ahead allocation), try A44 (Day-ahead)
                        if business_type is None or business_type.text != "A44":
                            # If neither A62 nor A44, skip this time series
                            continue

                    # Count prices
                    points = ts.findall(".//ns:Point", ns)
                    price_count += len(points)

                    # Get currency
                    currency = ts.find(".//ns:currency_Unit.name", ns)
                    if currency is not None:
                        metadata["currency"] = currency.text
                
                # Add price count to metadata
                metadata["price_count"] = price_count

            except Exception as e:
                _LOGGER.error(f"Failed to extract metadata from ENTSO-E XML: {e}")

        return metadata

    def _select_best_time_series(self, all_series: List) -> Optional[ET.Element]:
        """Select the best time series based on business type, resolution, and data quality.
        
        Args:
            all_series: List of TimeSeries elements
            
        Returns:
            Selected time series element or None if none found
        """
        # ENTSO-E namespace
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
        
        # Preference order for business types based on ENTSO-E API improvements
        business_type_preference = ["A62", "A44", "A65"]
        
        # Preference order for resolution (hourly is preferred for consistency)
        resolution_preference = ["PT60M", "PT30M", "PT15M"]
        
        # First, try to find the most suitable combination of business type and resolution
        best_series = []
        
        # First pass: find all series with preferred business types
        for btype in business_type_preference:
            candidates = []
            for series in all_series:
                business_type = series.find(".//ns:businessType", ns)
                if business_type is not None and business_type.text == btype:
                    candidates.append(series)
            
            if candidates:
                # If we found series with this business type, try to find the one with best resolution
                for resolution in resolution_preference:
                    for series in candidates:
                        period = series.find(".//ns:Period", ns)
                        if period is None:
                            continue
                            
                        res = period.find("ns:resolution", ns)
                        if res is not None and res.text == resolution:
                            best_series.append(series)
                
                # If we found any good candidates with this business type, return the best one
                if best_series:
                    # Evaluate data quality - choose the one with most points
                    best_count = 0
                    best_candidate = best_series[0]
                    
                    for series in best_series:
                        period = series.find(".//ns:Period", ns)
                        if period is None:
                            continue
                            
                        points = period.findall(".//ns:Point", ns)
                        if len(points) > best_count:
                            best_count = len(points)
                            best_candidate = series
                    
                    _LOGGER.debug(f"Selected ENTSO-E time series with business type {btype}, {best_count} points")
                    return best_candidate
                
                # If no perfect resolution match but we have candidates with this business type,
                # just return the first one since business type is more important than resolution
                if candidates:
                    _LOGGER.debug(f"Selected ENTSO-E time series with business type {btype} (no ideal resolution)")
                    return candidates[0]
        
        # If no series found with preferred business types, return the series with most data points
        if all_series:
            best_count = 0
            best_candidate = all_series[0]
            
            for series in all_series:
                period = series.find(".//ns:Period", ns)
                if period is None:
                    continue
                    
                points = period.findall(".//ns:Point", ns)
                if len(points) > best_count:
                    best_count = len(points)
                    best_candidate = series
            
            _LOGGER.debug(f"Selected ENTSO-E time series with {best_count} points (no preferred business type)")
            return best_candidate
        
        _LOGGER.warning("No suitable TimeSeries found in ENTSO-E response")
        return None

    def _parse_xml(self, xml_data: str) -> Dict[str, Any]:
        """Parse ENTSO-E XML response.
        
        Args:
            xml_data: XML response from ENTSO-E
            
        Returns:
            Parsed data with hourly prices
        """
        result = {
            "hourly_prices": {},
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
            
            if not time_series:
                _LOGGER.warning("No TimeSeries elements found in ENTSO-E response")
                return result
            
            # Select best time series
            selected_ts = self._select_best_time_series(time_series)
            
            if not selected_ts:
                _LOGGER.warning("No suitable TimeSeries found in ENTSO-E response")
                return result
            
            # Get currency
            currency = selected_ts.find(".//ns:currency_Unit.name", ns)
            if currency is not None:
                result["currency"] = currency.text
            
            # Get period start time
            period = selected_ts.find(".//ns:Period", ns)
            if period is None:
                _LOGGER.warning("No Period element found in ENTSO-E response")
                return result
                
            start_str = period.find(".//ns:timeInterval/ns:start", ns)
            if start_str is None:
                _LOGGER.warning("No start time found in ENTSO-E response")
                return result
                
            try:
                # Parse start time
                start_time = datetime.fromisoformat(start_str.text.replace('Z', '+00:00'))
                
                # Get resolution
                resolution = period.find(".//ns:resolution", ns)
                if resolution is None:
                    _LOGGER.warning("No resolution found in ENTSO-E response")
                    return result
                    
                res_text = resolution.text
                interval_hours = 1  # Default to 1 hour
                
                # Parse resolution (PT15M, PT30M, PT60M)
                if res_text == "PT15M":
                    interval_hours = 0.25
                elif res_text == "PT30M":
                    interval_hours = 0.5
                
                # Get price points
                points = period.findall(".//ns:Point", ns)
                
                # Parse points
                for point in points:
                    position = point.find("ns:position", ns)
                    price = point.find("ns:price.amount", ns)
                    
                    if position is not None and price is not None:
                        try:
                            pos = int(position.text)
                            price_val = float(price.text)
                            
                            # Calculate hour
                            point_time = start_time + timedelta(hours=(pos-1)*interval_hours)
                            
                            # Only keep hourly values for standardization
                            if interval_hours < 1:
                                # For sub-hourly resolution, only keep the hour mark (XX:00)
                                if point_time.minute != 0:
                                    continue
                            
                            # Format as ISO 8601
                            hour_key = point_time.isoformat()
                            
                            # Add to hourly prices
                            result["hourly_prices"][hour_key] = price_val
                            
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"Failed to parse point {position.text}: {e}")
                
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Failed to parse time information: {e}")
                
        except Exception as e:
            _LOGGER.error(f"Failed to parse ENTSO-E XML: {e}")
            
        return result

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from ENTSO-E API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

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
                                        from ...timezone.timezone_utils import normalize_hour_value
                                        normalized_hour, adjusted_date = normalize_hour_value(hour_time.hour, hour_time.date())

                                        # Create normalized hour key
                                        hour_key = f"{normalized_hour:02d}:00"
                                    except ValueError as e:
                                        # Skip invalid hours
                                        _LOGGER.warning(f"Skipping invalid hour value in ENTSOE data: {hour_time.hour}:00 - {e}")
                                        continue
                                    except ImportError as e:
                                        _LOGGER.warning(f"Import error for timezone utils: {e}, using original hour")
                                        hour_key = f"{hour_time.hour:02d}:00"

                                    # Add to hourly prices
                                    hourly_prices[hour_key] = price_val
                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning(f"Failed to parse point: {e}")

                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse start time: {e}")

            except Exception as e:
                _LOGGER.error(f"Failed to parse hourly prices from ENTSO-E XML: {e}")

        return hourly_prices

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

        now = datetime.now(timezone.utc)
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

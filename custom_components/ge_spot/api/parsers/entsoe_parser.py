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
        _LOGGER.debug(f"ENTSOE Parser: Input data type: {type(data).__name__}")
        if isinstance(data, dict):
            _LOGGER.debug(f"ENTSOE Parser: Input data keys: {list(data.keys())}")
            log_data_summary = {k: (f'{type(v).__name__} (len={len(v)})' if isinstance(v, (str, list, dict)) else v) for k, v in data.items()}
            _LOGGER.debug(f"ENTSOE Parser: Input data summary: {log_data_summary}")
        elif isinstance(data, str):
            _LOGGER.debug(f"ENTSOE Parser: Input data is string (len={len(data)})")

        result = {
            "hourly_raw": {},  # Standardized output key
            "currency": "EUR",
            "source": self.source
        }
        all_hourly_prices = {}  # Initialize aggregation dict

        # Parse XML response
        if isinstance(data, str) and "<Publication_MarketDocument" in data:
            _LOGGER.debug("ENTSOE Parser: Parsing single XML string")
            try:
                parsed_prices = self._parse_xml(data)
                if parsed_prices:
                    all_hourly_prices.update(parsed_prices.get("hourly_prices", {}))
                    result["currency"] = parsed_prices.get("currency", result["currency"])
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E XML: {e}", exc_info=True)

        # If data is a dictionary with "raw_data" key containing XML
        elif isinstance(data, dict) and "raw_data" in data and isinstance(data["raw_data"], str):
            _LOGGER.debug("ENTSOE Parser: Parsing XML from 'raw_data' key")
            try:
                if "<Publication_MarketDocument" in data["raw_data"]:
                    parsed_prices = self._parse_xml(data["raw_data"])
                    if parsed_prices:
                        all_hourly_prices.update(parsed_prices.get("hourly_prices", {}))
                        result["currency"] = parsed_prices.get("currency", result["currency"])
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E XML from raw_data: {e}", exc_info=True)

        # If data is a dictionary with multiple XML responses
        elif isinstance(data, dict) and "xml_responses" in data and isinstance(data["xml_responses"], list):
            xml_list = data["xml_responses"]
            _LOGGER.debug(f"ENTSOE Parser: Parsing list of {len(xml_list)} XML responses")
            for i, xml_response in enumerate(xml_list):
                _LOGGER.debug(f"ENTSOE Parser: XML content #{i+1} to parse:\n{xml_response[:1000]}...") # Log start of XML
                _LOGGER.debug(f"Parsing XML response #{i+1}")
                try:
                    parsed = self._parse_xml(xml_response)
                    _LOGGER.debug(f"ENTSOE Parser: _parse_xml result for XML #{i+1}: {parsed}")
                    if parsed and "hourly_prices" in parsed:
                        _LOGGER.debug(f"XML #{i+1} yielded {len(parsed['hourly_prices'])} price points")
                        all_hourly_prices.update(parsed["hourly_prices"])
                        if result["currency"] == "EUR" and "currency" in parsed:
                            result["currency"] = parsed["currency"]
                    else:
                        _LOGGER.debug(f"XML #{i+1} yielded no price points")
                except Exception as e:
                    _LOGGER.error(f"Failed to parse XML response #{i+1} from list: {e}", exc_info=True)

        # If hourly prices were already processed
        elif isinstance(data, dict) and "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            _LOGGER.debug("ENTSOE Parser: Using pre-existing 'hourly_prices' key")
            all_hourly_prices = data["hourly_prices"]
            if "currency" in data:
                result["currency"] = data["currency"]

        # Final assembly
        result["hourly_raw"] = all_hourly_prices
        _LOGGER.debug(f"ENTSOE Parser: Final aggregated hourly_raw size: {len(all_hourly_prices)}")
        _LOGGER.debug(f"ENTSOE Parser: Final hourly_raw content: {all_hourly_prices}")

        # Add current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_raw"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_raw"])

        # Add metadata
        metadata_source = data if isinstance(data, str) else (data.get("xml_responses", [None])[0] or data.get("raw_data"))
        if metadata_source:
            result["metadata"] = self.extract_metadata(metadata_source)
        else:
            result["metadata"] = self.extract_metadata({})

        # Add timezone info
        if isinstance(data, dict) and data.get("api_timezone"):
            result["timezone"] = data["api_timezone"]
        else:
            result["timezone"] = "Etc/UTC"

        # Validate the data
        if not self.validate_parsed_data(result):
            _LOGGER.warning(f"ENTSOE data validation failed for final result: {result}")

        _LOGGER.debug(f"ENTSOE Parser: Returning parsed data with keys: {list(result.keys())}")
        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        metadata = {
            "source": self.source,
            "currency": "EUR",
            "timezone": "Europe/Brussels",
        }

        if isinstance(data, str):
            try:
                root = ET.fromstring(data)
                ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
                time_series = root.findall(".//ns:TimeSeries", ns)
                price_count = 0

                for ts in time_series:
                    business_type = ts.find(".//ns:businessType", ns)
                    if business_type is None or business_type.text != "A62":
                        if business_type is None or business_type.text != "A44":
                            continue

                    points = ts.findall(".//ns:Point", ns)
                    price_count += len(points)

                    currency = ts.find(".//ns:currency_Unit.name", ns)
                    if currency is not None:
                        metadata["currency"] = currency.text

                metadata["price_count"] = price_count

            except Exception as e:
                _LOGGER.error(f"Failed to extract metadata from ENTSO-E XML: {e}")

        return metadata

    def _select_best_time_series(self, all_series: List) -> Optional[ET.Element]:
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
        business_type_preference = ["A44", "A65"]
        resolution_preference = ["PT60M", "PT30M", "PT15M"]
        best_series = []

        for btype in business_type_preference:
            candidates = []
            for series in all_series:
                business_type = series.find(".//ns:businessType", ns)
                if business_type is not None and business_type.text == btype:
                    candidates.append(series)

            if candidates:
                for resolution in resolution_preference:
                    for series in candidates:
                        period = series.find(".//ns:Period", ns)
                        if period is None:
                            continue

                        res = period.find("ns:resolution", ns)
                        if res is not None and res.text == resolution:
                            best_series.append(series)

                if best_series:
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

                if candidates:
                    _LOGGER.debug(f"Selected ENTSO-E time series with business type {btype} (no ideal resolution)")
                    return candidates[0]

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
        _LOGGER.debug("_parse_xml: Starting XML parsing")
        result = {
            "hourly_prices": {},
            "currency": "EUR",
            "source": self.source
        }

        try:
            root = ET.fromstring(xml_data)
            ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
            time_series = root.findall(".//ns:TimeSeries", ns)
            _LOGGER.debug(f"_parse_xml: Found {len(time_series)} TimeSeries elements")

            if not time_series:
                _LOGGER.warning("_parse_xml: No TimeSeries elements found in ENTSO-E response")
                return result

            selected_ts = self._select_best_time_series(time_series)

            if not selected_ts:
                _LOGGER.warning("_parse_xml: No suitable TimeSeries found by _select_best_time_series")
                return result

            _LOGGER.debug("_parse_xml: Selected a TimeSeries element")

            currency = selected_ts.find(".//ns:currency_Unit.name", ns)
            if currency is not None:
                result["currency"] = currency.text
                _LOGGER.debug(f"_parse_xml: Found currency: {result['currency']}")
            else:
                _LOGGER.debug("_parse_xml: Currency not found, defaulting to EUR")

            period = selected_ts.find(".//ns:Period", ns)
            if period is None:
                _LOGGER.warning("_parse_xml: No Period element found in selected TimeSeries")
                return result

            start_str_elem = period.find(".//ns:timeInterval/ns:start", ns)
            if start_str_elem is None or start_str_elem.text is None:
                _LOGGER.warning("_parse_xml: No start time found in Period element")
                return result
            start_str = start_str_elem.text
            _LOGGER.debug(f"_parse_xml: Found start time string: {start_str}")

            try:
                start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                _LOGGER.debug(f"_parse_xml: Parsed start_time: {start_time}")

                resolution_elem = period.find(".//ns:resolution", ns)
                if resolution_elem is None or resolution_elem.text is None:
                    _LOGGER.warning("_parse_xml: No resolution found in Period element")
                    return result

                res_text = resolution_elem.text
                _LOGGER.debug(f"_parse_xml: Found resolution: {res_text}")
                interval_hours = 1

                if res_text == "PT15M":
                    interval_hours = 0.25
                elif res_text == "PT30M":
                    interval_hours = 0.5
                elif res_text != "PT60M":
                    _LOGGER.warning(f"_parse_xml: Unexpected resolution '{res_text}', assuming hourly.")

                points = period.findall(".//ns:Point", ns)
                _LOGGER.debug(f"_parse_xml: Found {len(points)} Point elements")

                points_added = 0
                for point in points:
                    position_elem = point.find("ns:position", ns)
                    price_elem = point.find("ns:price.amount", ns)

                    if position_elem is not None and position_elem.text is not None and \
                       price_elem is not None and price_elem.text is not None:
                        try:
                            pos = int(position_elem.text)
                            price_val = float(price_elem.text)

                            point_time = start_time + timedelta(hours=(pos-1)*interval_hours)

                            if interval_hours < 1:
                                if point_time.minute != 0:
                                    continue

                            hour_key = point_time.isoformat()
                            result["hourly_prices"][hour_key] = price_val
                            points_added += 1
                            if points_added <= 3:
                                _LOGGER.debug(f"_parse_xml: Added point {pos}: key={hour_key}, price={price_val}")

                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"_parse_xml: Failed to parse point {position_elem.text}: {e}")
                    else:
                        _LOGGER.debug(f"_parse_xml: Skipping point with missing position or price")

                _LOGGER.debug(f"_parse_xml: Added {points_added} points to hourly_prices")

            except (ValueError, TypeError) as e:
                _LOGGER.error(f"_parse_xml: Failed to parse time information: {e}", exc_info=True)

        except ET.ParseError as e:
            _LOGGER.error(f"_parse_xml: Failed to parse XML structure: {e}", exc_info=True)
        except Exception as e:
            _LOGGER.error(f"_parse_xml: Unexpected error during XML parsing: {e}", exc_info=True)

        _LOGGER.debug(f"_parse_xml: Finished parsing. Returning {len(result['hourly_prices'])} prices.")
        return result

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, Any]:
        hourly_prices = {}

        if isinstance(data, str):
            try:
                root = ET.fromstring(data)
                ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
                time_series = root.findall(".//ns:TimeSeries", ns)
                for ts in time_series:
                    business_type = ts.find(".//ns:businessType", ns)
                    if business_type is None or business_type.text not in ["A62", "A44"]:
                        continue

                    period = ts.find(".//ns:Period", ns)
                    if period is None:
                        continue

                    start_str = period.find(".//ns:timeInterval/ns:start", ns)
                    if start_str is None:
                        continue

                    try:
                        start_time = datetime.fromisoformat(start_str.text.replace('Z', '+00:00'))
                        points = ts.findall(".//ns:Point", ns)

                        for point in points:
                            position = point.find("ns:position", ns)
                            price = point.find("ns:price.amount", ns)

                            if position is not None and price is not None:
                                try:
                                    pos = int(position.text)
                                    price_val = float(price.text)

                                    hour_time = start_time + timedelta(hours=pos-1)
                                    hour_key = hour_time.isoformat()
                                    hourly_prices[hour_key] = price_val

                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning(f"Failed to parse point: {e}")

                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse start time: {e}")

            except Exception as e:
                _LOGGER.error(f"Failed to parse hourly prices from ENTSO-E XML: {e}")

        return hourly_prices

    def _get_current_price(self, hourly_raw: Dict[str, float]) -> Optional[float]:
        """Get the current hour's price from the hourly_raw data."""
        return super()._get_current_price(hourly_raw)

    def _get_next_hour_price(self, hourly_raw: Dict[str, float]) -> Optional[float]:
        """Get the next hour's price from the hourly_raw data."""
        return super()._get_next_hour_price(hourly_raw)

    def _calculate_day_average(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Day average price or None if not enough data
        """
        if not hourly_prices:
            return None

        today = datetime.now(timezone.utc).date()
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                hour_dt = datetime.fromisoformat(hour_key)
                if hour_dt.date() == today:
                    today_prices.append(price)
            except (ValueError, TypeError):
                continue

        if len(today_prices) >= 12:
            return sum(today_prices) / len(today_prices)

        return None

# Add alias for backward compatibility with refactored code
EntsoePriceParser = EntsoeParser

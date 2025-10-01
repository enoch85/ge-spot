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
        super().__init__(timezone_service) # Pass timezone_service to base
        # Add any ENTSO-E specific initialization here

    def parse(self, data: Any) -> Dict[str, Any]:
        _LOGGER.debug(f"ENTSOE Parser: Received data of type: {type(data)}")
        all_interval_prices: Dict[str, float] = {}
        aggregated_currency: Optional[str] = None
        aggregated_timezone: Optional[str] = None # To store timezone if found in XML

        # Result structure
        result: Dict[str, Any] = {
            "interval_raw": {},
            "currency": None,
            "timezone": "Etc/UTC", # Default, might be overridden by _parse_xml
            "source": Source.ENTSOE,
            "metadata": {} # Initialize metadata
        }

        xml_to_parse: List[str] = []
        original_input_for_metadata = data # Keep original input for metadata if no XML is parsed

        if isinstance(data, str): # Single XML string
            _LOGGER.debug("ENTSOE Parser: Processing single XML string.")
            xml_to_parse.append(data)
        elif isinstance(data, list) and all(isinstance(item, str) for item in data): # List of XML strings
            _LOGGER.debug(f"ENTSOE Parser: Processing list of {len(data)} XML responses.")
            xml_to_parse.extend(data)
        elif isinstance(data, dict):
            _LOGGER.debug(f"ENTSOE Parser: Processing dict input. Keys: {list(data.keys())}")
            # Check for 'xml_responses' (list of XML strings) - common from FallbackManager
            if "xml_responses" in data and isinstance(data["xml_responses"], list):
                _LOGGER.debug("ENTSOE Parser: Found 'xml_responses' in dict.")
                for item in data["xml_responses"]:
                    if isinstance(item, str):
                        xml_to_parse.append(item)
                    else:
                        _LOGGER.warning(f"ENTSOE Parser: Non-string item in 'xml_responses': {type(item)}")
            # Check for 'raw_data' (single XML string) - common from API adapters or cache
            elif "raw_data" in data and isinstance(data["raw_data"], str):
                _LOGGER.debug("ENTSOE Parser: Found 'raw_data' string in dict.")
                xml_to_parse.append(data["raw_data"])
            # Check for 'document' (single XML string) - another possible key for raw XML
            elif "document" in data and isinstance(data["document"], str):
                 _LOGGER.debug("ENTSOE Parser: Found 'document' string in dict.")
                 xml_to_parse.append(data["document"])
            else:
                _LOGGER.warning("ENTSOE Parser: Dict input provided, but no recognized XML data found ('xml_responses', 'raw_data', or 'document').")
        else:
            _LOGGER.warning(f"ENTSOE Parser: Unparseable data type: {type(data)}. Cannot extract XML.")

        if not xml_to_parse:
            _LOGGER.warning("ENTSOE Parser: No XML data found to parse.")
            # result["interval_raw"] will be empty, which DataProcessor should handle
        else:
            _LOGGER.debug(f"ENTSOE Parser: Parsing {len(xml_to_parse)} XML document(s).")
            for i, xml_doc_str in enumerate(xml_to_parse):
                try:
                    # _parse_xml is expected to return:
                    # {"interval_prices": {"YYYY-MM-DDTHH:MM:SS+ZZ:ZZ": price, ...}, "currency": "EUR", "timezone": "Etc/UTC"}
                    parsed_single_xml = self._parse_xml(xml_doc_str)
                    if parsed_single_xml.get("interval_prices"):
                        all_interval_prices.update(parsed_single_xml["interval_prices"])
                        _LOGGER.debug(f"ENTSOE Parser: XML #{i+1} parsed, {len(parsed_single_xml['interval_prices'])} price points added.")
                        if parsed_single_xml.get("currency") and not aggregated_currency:
                            aggregated_currency = parsed_single_xml["currency"]
                        if parsed_single_xml.get("timezone") and not aggregated_timezone:
                            aggregated_timezone = parsed_single_xml["timezone"]
                    else:
                        _LOGGER.debug(f"ENTSOE Parser: XML #{i+1} yielded no price points.")
                except Exception as e:
                    _LOGGER.error(f"ENTSOE Parser: Failed to parse XML document #{i+1}: {e}", exc_info=True)

        result["interval_raw"] = all_interval_prices
        if aggregated_currency:
            result["currency"] = aggregated_currency
        if aggregated_timezone: # Use timezone from XML if found (should be UTC for ENTSO-E)
            result["timezone"] = aggregated_timezone
        
        # Metadata Extraction
        # Use the first XML doc for metadata if multiple were parsed.
        # If no XML was parsed but input was a dict, try to extract from that.
        metadata_source_for_extraction = None
        if xml_to_parse:
            metadata_source_for_extraction = xml_to_parse[0]
        elif isinstance(original_input_for_metadata, dict): # If input was a dict and no XML found
             metadata_source_for_extraction = original_input_for_metadata
        
        if metadata_source_for_extraction is not None:
            result["metadata"] = self.extract_metadata(metadata_source_for_extraction)
        else:
            result["metadata"] = self.extract_metadata({}) # Fallback to empty metadata

        # Current/Next interval prices (BasePriceParser methods expect UTC ISO keys if tz_service is UTC)
        # Since ENTSO-E interval_raw keys are UTC ISO, this should work correctly.
        result["current_price"] = self._get_current_price(result["interval_raw"])
        result["next_interval_price"] = self._get_next_interval_price(result["interval_raw"])

        _LOGGER.debug(f"ENTSOE Parser: Final aggregated interval_raw size: {len(all_interval_prices)}")
        _LOGGER.debug(f"ENTSOE Parser: Final currency: {result['currency']}, Final timezone: {result['timezone']}")
        # _LOGGER.debug(f"ENTSOE Parser: Final interval_raw content for {result['source']}: {all_interval_prices}") # Can be too verbose

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
        # Prioritize 15-minute intervals, then 30-minute, then hourly
        resolution_preference = ["PT15M", "PT30M", "PT60M"]
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
            Parsed data with interval prices
        """
        _LOGGER.debug("_parse_xml: Starting XML parsing")
        result = {
            "interval_prices": {},
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

                            # Accept all interval times (15-min, 30-min, hourly)
                            interval_key = point_time.isoformat()
                            result["interval_prices"][interval_key] = price_val
                            points_added += 1
                            if points_added <= 3:
                                _LOGGER.debug(f"_parse_xml: Added point {pos}: key={interval_key}, price={price_val}")

                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"_parse_xml: Failed to parse point {position_elem.text}: {e}")
                    else:
                        _LOGGER.debug(f"_parse_xml: Skipping point with missing position or price")

                _LOGGER.debug(f"_parse_xml: Added {points_added} points to interval_prices")

            except (ValueError, TypeError) as e:
                _LOGGER.error(f"_parse_xml: Failed to parse time information: {e}", exc_info=True)

        except ET.ParseError as e:
            _LOGGER.error(f"_parse_xml: Failed to parse XML structure: {e}", exc_info=True)
        except Exception as e:
            _LOGGER.error(f"_parse_xml: Unexpected error during XML parsing: {e}", exc_info=True)

        _LOGGER.debug(f"_parse_xml: Finished parsing. Returning {len(result['interval_prices'])} prices.")
        return result

    def parse_interval_prices(self, data: Any, area: str) -> Dict[str, Any]:
        interval_prices = {}

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
                        resolution_elem = period.find(".//ns:resolution", ns)
                        interval_hours = 1  # Default to hourly
                        
                        if resolution_elem is not None and resolution_elem.text:
                            if resolution_elem.text == "PT15M":
                                interval_hours = 0.25
                            elif resolution_elem.text == "PT30M":
                                interval_hours = 0.5
                        
                        points = ts.findall(".//ns:Point", ns)

                        for point in points:
                            position = point.find("ns:position", ns)
                            price = point.find("ns:price.amount", ns)

                            if position is not None and price is not None:
                                try:
                                    pos = int(position.text)
                                    price_val = float(price.text)

                                    interval_time = start_time + timedelta(hours=(pos-1)*interval_hours)
                                    interval_key = interval_time.isoformat()
                                    interval_prices[interval_key] = price_val

                                except (ValueError, TypeError) as e:
                                    _LOGGER.warning(f"Failed to parse point: {e}")

                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse start time: {e}")

            except Exception as e:
                _LOGGER.error(f"Failed to parse interval prices from ENTSO-E XML: {e}")

        return interval_prices

    def _get_current_price(self, interval_raw: Dict[str, float]) -> Optional[float]:
        """Get the current interval's price from the interval_raw data."""
        return super()._get_current_price(interval_raw)

    def _get_next_interval_price(self, interval_raw: Dict[str, float]) -> Optional[float]:
        """Get the next interval's price from the interval_raw data."""
        if not interval_raw:
            return None

        now = datetime.now(timezone.utc)
        # Round down to current 15-minute interval, then add 15 minutes
        minute_rounded = (now.minute // 15) * 15
        current_interval = now.replace(minute=minute_rounded, second=0, microsecond=0)
        next_interval = current_interval + timedelta(minutes=15)
        next_interval_key = next_interval.isoformat()

        return interval_raw.get(next_interval_key)

    def _calculate_day_average(self, interval_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            interval_prices: Dictionary of interval prices

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

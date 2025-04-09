"""API handler for ENTSO-E Transparency Platform."""
import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from .base import BaseEnergyAPI
from ..timezone import ensure_timezone_aware
from ..const import (
    AreaMapping,
    Config,
    EntsoE,
    Network,
    TimeFormat,
    EnergyUnit,
    ContentType,
    TimeInterval
)

_LOGGER = logging.getLogger(__name__)

class EntsoEAPI(BaseEnergyAPI):
    """API handler for ENTSO-E Transparency Platform."""

    BASE_URL = Network.URLs.ENTSOE

    async def _fetch_data(self):
        """Fetch data from ENTSO-E."""
        api_key = self.config.get(Config.API_KEY) or self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            return None

        now = self._get_now()
        today = now
        tomorrow = today + datetime.timedelta(days=1)

        # Format dates for ENTSO-E API (YYYYMMDDHHMM format)
        # Use 01:00 (1 AM) as the time part as shown in the ENTSO-E examples
        period_start = today.strftime(TimeFormat.ENTSOE_DATE_HOUR)
        period_end = tomorrow.strftime(TimeFormat.ENTSOE_DATE_HOUR)

        # Get area code - map our area code to ENTSO-E area code without default
        area = self.config.get("area")
        if not area:
            _LOGGER.error("No area provided in configuration")
            return None

        # Try to use the mapped ENTSOE code if available
        entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)

        _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

        # Build query parameters according to ENTSO-E API requirements
        params = {
            "securityToken": api_key,
            "documentType": EntsoE.DOCUMENT_TYPE_DAY_AHEAD,
            "in_Domain": entsoe_area,
            "out_Domain": entsoe_area,
            "periodStart": period_start,
            "periodEnd": period_end,
        }

        _LOGGER.debug(f"Fetching ENTSO-E with params: periodStart={period_start}, periodEnd={period_end}, area={entsoe_area}, API key starting with {api_key[:5]}...")

        # Use custom headers for ENTSO-E API
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
            "Content-Type": ContentType.XML
        }

        response = await self.data_fetcher.fetch_with_retry(
            self.BASE_URL,
            params=params,
            headers=headers,
            timeout=Network.Defaults.TIMEOUT,
            max_retries=Network.Defaults.RETRY_COUNT
        )

        if not response:
            _LOGGER.error("ENTSO-E API returned empty response after all retries")
            return None

        # Check for authentication errors in the response
        if "Not authorized" in response:
            _LOGGER.error(f"ENTSO-E API authentication failed: Not authorized. Check your API key.")
            return None
        elif "No matching data found" in response:
            _LOGGER.warning(f"ENTSO-E API returned: No matching data found for the query parameters")
            return None

        return response

    async def _process_data(self, data):
        """Process the data from ENTSO-E with correct XML namespace handling."""
        if not data:
            return None

        try:
            # The XML has a default namespace which must be handled explicitly
            # Define our namespace map
            nsmap = {
                EntsoE.XMLNS_NS: EntsoE.NS_URN
            }

            # Parse XML
            root = ET.fromstring(data)

            # Find TimeSeries elements using explicit namespace
            time_series_elements = root.findall(f".//{EntsoE.XMLNS_NS}:TimeSeries", nsmap)

            if not time_series_elements:
                _LOGGER.error("No TimeSeries elements found in ENTSO-E response")
                _LOGGER.debug(f"First 500 chars of XML: {data[:500]}")
                return None

            now = self._get_now()
            current_hour = now.hour

            # We'll store data from all TimeSeries in these dictionaries keyed by hour-string
            # This way we can compare and choose the correct prices
            all_hourly_prices = []

            _LOGGER.debug(f"Found {len(time_series_elements)} TimeSeries elements in ENTSO-E response")

            # Process each TimeSeries separately to compare them
            for ts_index, ts in enumerate(time_series_elements):
                # Extract TimeSeries metadata for identification
                business_type = self._find_element_text(ts, f".//{EntsoE.XMLNS_NS}:businessType", nsmap, "unknown")
                curve_type = self._find_element_text(ts, f".//{EntsoE.XMLNS_NS}:curveType", nsmap, "unknown")
                currency = self._find_element_text(ts, f".//{EntsoE.XMLNS_NS}:currency_Unit.name", nsmap, "EUR")
                unit_name = self._find_element_text(ts, f".//{EntsoE.XMLNS_NS}:price_Measure_Unit.name", nsmap, "unknown")

                _LOGGER.debug(f"TimeSeries {ts_index+1}: businessType={business_type}, curveType={curve_type}, "
                             f"currency={currency}, measureUnit={unit_name}")

                # Find Period elements
                period_elements = ts.findall(f".//{EntsoE.XMLNS_NS}:Period", nsmap)
                if not period_elements:
                    _LOGGER.debug(f"No Period elements found in TimeSeries {ts_index+1}")
                    continue

                # Process this TimeSeries
                hourly_prices = {}
                raw_prices = []

                for period in period_elements:
                    # Extract timeInterval
                    interval = period.find(f"{EntsoE.XMLNS_NS}:timeInterval", nsmap)
                    if interval is None:
                        continue

                    # Get start and end times
                    start_element = interval.find(f"{EntsoE.XMLNS_NS}:start", nsmap)
                    end_element = interval.find(f"{EntsoE.XMLNS_NS}:end", nsmap)

                    if start_element is None or end_element is None:
                        continue

                    # Parse times
                    try:
                        start_dt = datetime.datetime.fromisoformat(start_element.text.replace("Z", "+00:00"))
                        end_dt = datetime.datetime.fromisoformat(end_element.text.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                    # Get resolution
                    resolution_element = period.find(f"{EntsoE.XMLNS_NS}:resolution", nsmap)
                    resolution = TimeInterval.HOURLY  # Default hourly
                    if resolution_element is not None:
                        resolution = resolution_element.text

                    # Handle different resolutions
                    if resolution == TimeInterval.QUARTER_HOURLY:
                        resolution_minutes = 15
                    elif resolution == TimeInterval.HOURLY or resolution == "PT1H":
                        resolution_minutes = 60
                    else:
                        resolution_minutes = 60

                    # Process Point elements
                    points = period.findall(f"{EntsoE.XMLNS_NS}:Point", nsmap)
                    position_prices = {}

                    for point in points:
                        position_element = point.find(f"{EntsoE.XMLNS_NS}:position", nsmap)
                        price_element = point.find(f"{EntsoE.XMLNS_NS}:price.amount", nsmap)

                        if position_element is None or price_element is None:
                            continue

                        try:
                            position = int(position_element.text)
                            price = float(price_element.text)
                            position_prices[position] = price
                        except (ValueError, TypeError):
                            continue

                    # Process each position
                    for position, price in position_prices.items():
                        position_minutes = (position - 1) * resolution_minutes
                        position_time = start_dt + datetime.timedelta(minutes=position_minutes)

                        # Convert to local time
                        local_time = self._convert_to_local(position_time)
                        hour_str = local_time.strftime(TimeFormat.HOUR_ONLY)

                        # Debug the timezone conversion
                        _LOGGER.debug(f"Position time: {position_time.isoformat()} → Local time: {local_time.isoformat()}")

                        # Store in hourly prices
                        if hour_str not in hourly_prices:
                            hourly_prices[hour_str] = price

                # Store this TimeSeries prices for comparison
                if hourly_prices:
                    all_hourly_prices.append({
                        "metadata": {
                            "business_type": business_type,
                            "curve_type": curve_type,
                            "currency": currency,
                            "unit": unit_name,
                            "index": ts_index
                        },
                        "prices": hourly_prices
                    })

            # If we have multiple TimeSeries, select the correct one
            # For SE4 with EUR, the actual spot prices are usually the day-ahead allocation (A62)
            # with the lowest values around peak hours
            selected_series = self._select_best_time_series(all_hourly_prices)

            if not selected_series:
                _LOGGER.error("Failed to identify any valid price TimeSeries")
                return None

            # Now process the selected series completely
            _LOGGER.info(f"Selected TimeSeries with businessType={selected_series['metadata']['business_type']}, "
                        f"index={selected_series['metadata']['index']} for price data")

            hourly_prices = selected_series["prices"]  # These are the raw prices
            currency = selected_series["metadata"]["currency"]

            final_hourly_prices = {}
            all_converted_prices = []
            raw_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}

            # Process each hour in the selected series
            for hour_str, price in hourly_prices.items():
                hour = int(hour_str.split(":")[0])

                # Create timestamps for the raw prices array
                today = now.date()
                hour_time = datetime.datetime.combine(today, datetime.time(hour=hour))
                hour_time = self._convert_to_local(hour_time)
                end_time = hour_time + datetime.timedelta(hours=1)

                # Store raw price
                raw_prices.append({
                    "start": hour_time.isoformat(),
                    "end": end_time.isoformat(),
                    "price": price
                })

                # Convert price using the centralized method
                converted_price = await self._convert_price(
                    price=price,
                    from_currency=currency,
                    from_unit=EnergyUnit.MWH
                )

                # Store converted price
                final_hourly_prices[hour_str] = converted_price
                all_converted_prices.append(converted_price)

                # Check if this is current hour
                if hour == current_hour:
                    current_price = converted_price
                    raw_values["current_price"] = {
                        "raw": price,
                        "converted": converted_price,
                        "hour": current_hour
                    }

                # Check if this is next hour
                next_hour = (current_hour + 1) % 24
                if hour == next_hour:
                    next_hour_price = converted_price
                    raw_values["next_hour_price"] = {
                        "raw": price,
                        "converted": converted_price,
                        "hour": next_hour
                    }

            # Calculate statistics
            day_average_price = sum(all_converted_prices) / len(all_converted_prices) if all_converted_prices else None
            peak_price = max(all_converted_prices) if all_converted_prices else None
            off_peak_price = min(all_converted_prices) if all_converted_prices else None

            # Store raw value details for statistics
            raw_values["day_average_price"] = {"value": day_average_price}
            raw_values["peak_price"] = {"value": peak_price}
            raw_values["off_peak_price"] = {"value": off_peak_price}

            # Ensure we have data for current hour
            if current_price is None and final_hourly_prices:
                _LOGGER.warning(f"Current hour price not found, using first available hour")
                current_hour_str = f"{current_hour:02d}:00"
                if current_hour_str in final_hourly_prices:
                    current_price = final_hourly_prices[current_hour_str]
                else:
                    # Use first available price
                    first_hour = list(final_hourly_prices.keys())[0]
                    current_price = final_hourly_prices[first_hour]

            # Ensure we have data for next hour
            if next_hour_price is None and final_hourly_prices:
                next_hour_str = f"{next_hour:02d}:00"
                if next_hour_str in final_hourly_prices:
                    next_hour_price = final_hourly_prices[next_hour_str]

            return {
                "current_price": current_price,
                "next_hour_price": next_hour_price,
                "day_average_price": day_average_price,
                "peak_price": peak_price,
                "off_peak_price": off_peak_price,
                "hourly_prices": final_hourly_prices,
                "raw_prices": raw_prices,
                "raw_values": raw_values,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "api_key_valid": True,
                "currency": self._currency
            }
        except ET.ParseError as e:
            _LOGGER.error(f"Error parsing ENTSO-E XML: {e}")
            # Add more context for debugging
            if data and len(data) > 200:
                _LOGGER.debug(f"First 200 chars of XML: {data[:200]}...")
            return None
        except Exception as e:
            _LOGGER.error(f"Error processing ENTSO-E data: {e}", exc_info=True)
            return None

    def _select_best_time_series(self, all_series):
        """Select the best TimeSeries to use for price data.

        For ENTSO-E, the XML can contain multiple TimeSeries elements with different data.
        We need to determine which one contains the actual spot prices.
        """
        if not all_series:
            return None

        # If only one series, use it
        if len(all_series) == 1:
            return all_series[0]

        # First try to identify by businessType
        # A62 (Day-ahead allocation) is generally the correct spot price data
        for series in all_series:
            if series["metadata"]["business_type"] == EntsoE.BUSINESS_TYPE_DAY_AHEAD_ALLOCATION:
                _LOGGER.debug(f"Selected TimeSeries with businessType={EntsoE.BUSINESS_TYPE_DAY_AHEAD_ALLOCATION} (Day-ahead allocation)")
                return series

        # Next, try A44 (Day-ahead)
        for series in all_series:
            if series["metadata"]["business_type"] == EntsoE.BUSINESS_TYPE_DAY_AHEAD:
                _LOGGER.debug(f"Selected TimeSeries with businessType={EntsoE.BUSINESS_TYPE_DAY_AHEAD} (Day-ahead)")
                return series

        # If still not found, use a heuristic approach - spot price TimeSeries
        # often has the lowest values at peak hours compared to other TimeSeries

        # For most electricity markets, prices are lower overnight
        # Get average of overnight hours for each series
        overnight_averages = []

        for series in all_series:
            overnight_prices = []
            for hour_str, price in series["prices"].items():
                hour = int(hour_str.split(":")[0])
                # Consider 0-6 as overnight hours
                if 0 <= hour <= 6:
                    overnight_prices.append(price)

            # Calculate average if we have prices
            if overnight_prices:
                avg = sum(overnight_prices) / len(overnight_prices)
                overnight_averages.append({
                    "series": series,
                    "overnight_avg": avg
                })

        # Choose the series with the lowest overnight average
        if overnight_averages:
            overnight_averages.sort(key=lambda x: x["overnight_avg"])
            _LOGGER.debug(f"Selected TimeSeries with lowest overnight prices (avg={overnight_averages[0]['overnight_avg']})")
            return overnight_averages[0]["series"]

        # If all else fails, use the first series
        _LOGGER.debug("Falling back to first TimeSeries")
        return all_series[0]

    def _find_element_text(self, element, path, nsmap, default=None):
        """Helper method to safely extract text from an element."""
        child = element.find(path, nsmap)
        if child is not None:
            return child.text
        return default

    def _convert_to_local(self, dt):
        """Convert UTC datetime to local timezone."""
        dt = ensure_timezone_aware(dt)

        # If we have Home Assistant instance, use its timezone
        if hasattr(self, 'hass') and self.hass:
            from homeassistant.util import dt as dt_util
            local_dt = dt_util.as_local(dt)
            _LOGGER.debug(f"Converting {dt.isoformat()} to local time: {local_dt.isoformat()}")
            return local_dt

        # Otherwise use system local time
        local_dt = dt.astimezone()
        _LOGGER.debug(f"Converting {dt.isoformat()} to system local time: {local_dt.isoformat()}")
        return local_dt

    @staticmethod
    def is_area_supported(area: str) -> bool:
        """Check if an area is supported by ENTSO-E."""
        return area in AreaMapping.ENTSOE_MAPPING

    @staticmethod
    async def validate_api_key(api_key, area, session=None):
        """Validate an API key by making a test request.

        Args:
            api_key: The ENTSO-E API key to validate
            area: The area code to test with
            session: Optional aiohttp session

        Returns:
            bool: True if the API key is valid, False otherwise
        """
        try:
            # Create a temporary API instance
            config = {
                "area": area,
                "api_key": api_key
            }
            api = EntsoEAPI(config)

            # Use provided session if available
            if session:
                api.session = session
                api._owns_session = False

            # Try to fetch some data with the provided key
            _LOGGER.debug(f"Validating ENTSO-E API key for area {area}")
            result = await api._fetch_data()

            # Close session if we created one
            if api._owns_session:
                await api.close()

            # Check if we got a valid response
            if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
                _LOGGER.debug("ENTSO-E API key validation successful")
                return True
            elif isinstance(result, str) and "Not authorized" in result:
                _LOGGER.error("API key validation failed: Not authorized")
                return False
            elif isinstance(result, str) and "No matching data found" in result:
                # This is technically a valid API key, even if there's no data
                _LOGGER.warning("API key is valid but no data available for the specified area")
                return True
            else:
                _LOGGER.error("API key validation failed: No valid data returned")
                return False

        except Exception as e:
            _LOGGER.error(f"API key validation error: {e}")
            return False

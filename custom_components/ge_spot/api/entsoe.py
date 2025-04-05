import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, convert_energy_price
from ..const import ENTSOE_AREA_MAPPING, CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

class EntsoEAPI(BaseEnergyAPI):
    """API handler for ENTSO-E Transparency Platform."""

    # Updated URL based on official documentation
    BASE_URL = "https://web-api.tp.entsoe.eu/api"

    async def _fetch_data(self):
        """Fetch data from ENTSO-E."""
        api_key = self.config.get(CONF_API_KEY) or self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            return None

        now = self._get_now()
        today = now
        tomorrow = today + datetime.timedelta(days=1)

        # Format dates for ENTSO-E API
        # Use 22:00 (10 PM) as the time part as shown in the ENTSO-E examples
        period_start = today.strftime("%Y%m%d2200")
        period_end = tomorrow.strftime("%Y%m%d2200")

        # Get area code - map our area code to ENTSO-E area code without default
        area = self.config.get("area")
        if not area:
            _LOGGER.error("No area provided in configuration")
            return None

        # Try to use the mapped ENTSOE code if available
        entsoe_area = ENTSOE_AREA_MAPPING.get(area, area)

        _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

        # Build query parameters according to ENTSO-E API requirements
        params = {
            "securityToken": api_key,
            "documentType": "A44",  # Day-ahead prices
            "in_Domain": entsoe_area,
            "out_Domain": entsoe_area,
            "periodStart": period_start,
            "periodEnd": period_end,
        }

        _LOGGER.debug(f"Fetching ENTSO-E with params: periodStart={period_start}, periodEnd={period_end}, area={entsoe_area}, API key starting with {api_key[:5]}...")

        # Use custom headers for ENTSO-E API
        headers = {
            "User-Agent": "HomeAssistantGESpot/1.0",
            "Accept": "application/xml;charset=UTF-8",
            "Content-Type": "application/xml;charset=UTF-8"
        }

        try:
            await self._ensure_session()

            if not self.session or self.session.closed:
                _LOGGER.error("No valid session for ENTSO-E API request")
                return None

            url = self.BASE_URL
            response = None
            retries = 3

            for attempt in range(retries):
                try:
                    # Full URL with parameters for debugging (hide full API key)
                    masked_key = f"{api_key[:5]}..." if len(api_key) > 5 else "***"
                    full_url = f"{url}?securityToken={masked_key}&documentType=A44&in_Domain={entsoe_area}&out_Domain={entsoe_area}&periodStart={period_start}&periodEnd={period_end}"
                    _LOGGER.debug(f"ENTSO-E request attempt {attempt+1}: {full_url}")

                    async with self.session.get(url, params=params, headers=headers, timeout=60) as resp:
                        status_code = resp.status
                        content_type = resp.headers.get('Content-Type', '')
                        _LOGGER.debug(f"ENTSO-E response status: {status_code}, content-type: {content_type}")

                        if status_code == 200:
                            response = await resp.text()
                            _LOGGER.debug(f"ENTSO-E response: received {len(response)} bytes")
                            if "<Publication_MarketDocument" in response:
                                _LOGGER.debug("ENTSO-E response contains valid XML document")
                                break
                            else:
                                _LOGGER.warning("ENTSO-E response does not contain expected XML document")
                                if len(response) < 500:
                                    _LOGGER.debug(f"Response content: {response}")

                        elif status_code == 401 or status_code == 403:
                            error_text = await resp.text()
                            _LOGGER.error(f"ENTSO-E API authentication failed ({status_code}). Check your API key. Response: {error_text[:200]}")
                            break  # No point retrying with same credentials

                        else:
                            error_text = await resp.text()
                            _LOGGER.error(f"ENTSO-E API request failed with status {status_code}: {error_text[:200]}")
                            if attempt < retries - 1:
                                delay = 2 ** attempt
                                _LOGGER.debug(f"Retrying in {delay} seconds...")
                                await asyncio.sleep(delay)

                except asyncio.TimeoutError:
                    _LOGGER.error(f"Timeout fetching from ENTSO-E (attempt {attempt+1}/{retries})")
                    if attempt < retries - 1:
                        delay = 2 ** attempt
                        await asyncio.sleep(delay)

                except Exception as e:
                    _LOGGER.error(f"Error during ENTSO-E API request (attempt {attempt+1}/{retries}): {e}")
                    if attempt < retries - 1:
                        delay = 2 ** attempt
                        await asyncio.sleep(delay)

            # Check for authentication errors in the response
            if response:
                if "Not authorized" in response:
                    _LOGGER.error(f"ENTSO-E API authentication failed: Not authorized. Check your API key.")
                    return None
                elif "No matching data found" in response:
                    _LOGGER.warning(f"ENTSO-E API returned: No matching data found for the query parameters")
                    return None

                return response
            else:
                _LOGGER.error("ENTSO-E API returned empty response after all retries")
                return None

        except Exception as e:
            _LOGGER.error(f"Failed to fetch data from ENTSO-E: {e}")
            return None

    async def _process_data(self, data):
        """Process the data from ENTSO-E."""
        if not data:
            return None

        try:
            # Updated namespace to match API response
            ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

            # Parse XML
            root = ET.fromstring(data)

            # Find TimeSeries elements
            time_series_elements = root.findall(".//ns:TimeSeries", ns)

            if not time_series_elements:
                # Try without namespace - handle default namespace case
                time_series_elements = root.findall(".//TimeSeries")

            if not time_series_elements:
                _LOGGER.error("No TimeSeries elements found in ENTSO-E response")
                # Log a sample of the XML for debugging
                _LOGGER.debug(f"XML snippet: {data[:500]}...")
                return None

            now = self._get_now()
            hourly_prices = {}
            all_prices = []
            raw_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}

            use_cents = self.config.get("price_in_cents", False)

            # Process each TimeSeries element
            for ts in time_series_elements:
                # Get period elements with namespace
                period_elements = ts.findall(".//ns:Period", ns)

                # If not found with namespace, try without
                if not period_elements:
                    period_elements = ts.findall(".//Period")

                for period in period_elements:
                    # Get resolution (PT15M for 15 minutes, PT60M for 60 minutes)
                    resolution_element = period.find("ns:resolution", ns) or period.find("resolution")
                    if resolution_element is None:
                        _LOGGER.warning("Missing resolution element in period")
                        continue

                    resolution = resolution_element.text
                    resolution_minutes = 60  # Default to hourly

                    if resolution == "PT15M":
                        resolution_minutes = 15
                    elif resolution == "PT60M" or resolution == "PT1H":
                        resolution_minutes = 60
                    else:
                        _LOGGER.warning(f"Unknown resolution: {resolution}, defaulting to hourly")

                    # Get time interval
                    interval = period.find("ns:timeInterval", ns) or period.find("timeInterval")
                    if interval is None:
                        _LOGGER.warning("Missing timeInterval in period")
                        continue

                    # Find start and end with or without namespace
                    start_element = interval.find("ns:start", ns) or interval.find("start")
                    end_element = interval.find("ns:end", ns) or interval.find("end")

                    if start_element is None or end_element is None:
                        _LOGGER.warning("Missing start or end in timeInterval")
                        continue

                    start_text = start_element.text
                    end_text = end_element.text

                    try:
                        start_dt = datetime.datetime.fromisoformat(start_text.replace("Z", "+00:00"))
                        end_dt = datetime.datetime.fromisoformat(end_text.replace("Z", "+00:00"))
                    except ValueError as e:
                        _LOGGER.error(f"Error parsing datetime: {e}")
                        continue

                    # Process points
                    points = period.findall("ns:Point", ns) or period.findall("Point")

                    # Create a mapping of positions to prices
                    position_price_map = {}
                    for point in points:
                        position_element = point.find("ns:position", ns) or point.find("position")
                        price_element = point.find("ns:price.amount", ns) or point.find("price.amount")

                        if position_element is None or price_element is None:
                            _LOGGER.warning(f"Missing position or price.amount in point")
                            continue

                        try:
                            position = int(position_element.text)
                            price = float(price_element.text)
                            position_price_map[position] = price
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"Invalid position or price value: {e}")

                    # Calculate total positions based on resolution and time interval
                    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
                    expected_positions = total_minutes // resolution_minutes

                    # Process each position and map to actual datetime
                    for position in range(1, expected_positions + 1):
                        if position not in position_price_map:
                            _LOGGER.debug(f"Missing price data for position {position}")
                            continue

                        price = position_price_map[position]

                        # Calculate the datetime for this position
                        position_minutes = (position - 1) * resolution_minutes
                        position_time = start_dt + datetime.timedelta(minutes=position_minutes)
                        position_end = position_time + datetime.timedelta(minutes=resolution_minutes)

                        # Store raw price data
                        raw_prices.append({
                            "start": position_time.isoformat(),
                            "end": position_end.isoformat(),
                            "price": price
                        })

                        # Convert price from EUR/MWh to the appropriate currency/unit
                        converted_price = await self._convert_price(
                            price=price,
                            from_unit="MWh",
                            from_currency="EUR",
                            to_currency=self._currency,
                            to_subunit=use_cents
                        )

                        # If 15-minute resolution, average to hourly for consistent representation
                        if resolution_minutes == 15:
                            # Get the start of the hour
                            hour_start = position_time.replace(minute=0, second=0, microsecond=0)
                            hour_key = hour_start.strftime("%Y-%m-%d %H:00")

                            # Initialize or update hourly average
                            if hour_key not in hourly_prices:
                                hourly_prices[hour_key] = {"sum": converted_price, "count": 1}
                            else:
                                hourly_prices[hour_key]["sum"] += converted_price
                                hourly_prices[hour_key]["count"] += 1
                        else:
                            # For hourly data, store directly
                            hour_key = position_time.strftime("%Y-%m-%d %H:00")
                            hourly_prices[hour_key] = {"sum": converted_price, "count": 1}

                        # Store in all_prices list for later statistics
                        all_prices.append(converted_price)

            # Process hourly prices to calculate final values
            final_hourly_prices = {}
            for hour_key, data in hourly_prices.items():
                avg_price = data["sum"] / data["count"]
                dt = datetime.datetime.strptime(hour_key, "%Y-%m-%d %H:00")
                hour_str = f"{dt.hour:02d}:00"
                final_hourly_prices[hour_str] = avg_price

                # Check if this is current hour
                if dt.hour == now.hour and dt.date() == now.date():
                    current_price = avg_price
                    raw_values["current_price"] = {
                        "raw": data["sum"] / data["count"],  # Average raw price
                        "converted": avg_price,
                        "hour": dt.hour
                    }

                # Check if this is next hour
                next_hour = (now.replace(minute=0, second=0, microsecond=0) +
                            datetime.timedelta(hours=1))
                if dt.hour == next_hour.hour and dt.date() == next_hour.date():
                    next_hour_price = avg_price
                    raw_values["next_hour_price"] = {
                        "raw": data["sum"] / data["count"],  # Average raw price
                        "converted": avg_price,
                        "hour": dt.hour
                    }

            # Calculate day average
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None

            # Find peak and off-peak prices
            peak_price = max(all_prices) if all_prices else None
            off_peak_price = min(all_prices) if all_prices else None

            # Store raw values for statistics
            raw_values["day_average_price"] = {
                "value": day_average_price,
                "calculation": "average of all hourly prices"
            }

            raw_values["peak_price"] = {
                "value": peak_price,
                "calculation": "maximum of all hourly prices"
            }

            raw_values["off_peak_price"] = {
                "value": off_peak_price,
                "calculation": "minimum of all hourly prices"
            }

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
                "api_key_valid": True
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

    @staticmethod
    def is_area_supported(area: str) -> bool:
        """Check if an area is supported by ENTSO-E."""
        return area in ENTSOE_AREA_MAPPING

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

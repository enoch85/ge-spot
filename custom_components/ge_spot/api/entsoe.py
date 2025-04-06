"""API handler for ENTSO-E Transparency Platform."""
import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, async_convert_energy_price
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
        # Use 01:00 (1 AM) as the time part as shown in the ENTSO-E examples
        period_start = today.strftime("%Y%m%d0100")
        period_end = tomorrow.strftime("%Y%m%d0100")

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

    def _identify_price_time_series(self, time_series_elements, nsmap):
        """Identify the TimeSeries element containing day-ahead prices.
        
        ENTSO-E returns multiple TimeSeries elements with different business types
        and interpretations. We need to select the one with actual day-ahead prices.
        
        Priority order:
        1. Day-ahead allocation (A62)
        2. Day-ahead prices (A44)
        3. Final day-ahead (A65)
        4. First TimeSeries as fallback
        """
        # Priority map for businessType - lower number means higher priority
        business_types = {
            "A62": 1,  # Day-ahead allocation
            "A44": 2,  # Day-ahead
            "A65": 3,  # Final day-ahead
        }
        
        candidate_series = []
        
        for ts in time_series_elements:
            # Extract business type and other metadata
            business_type = self._find_element_text(ts, ".//ns:businessType", nsmap)
            curve_type = self._find_element_text(ts, ".//ns:curveType", nsmap)
            price_measure = self._find_element_text(ts, ".//ns:price_Measure_Unit.name", nsmap)
            
            # Skip series with invalid price measure unit
            if price_measure and price_measure not in ["MWH", "EUR"]:
                continue
                
            # Track as candidate with priority score (lower is better)
            priority = business_types.get(business_type, 100)
            
            # Store relevant metadata
            candidate_series.append({
                "element": ts,
                "business_type": business_type,
                "curve_type": curve_type,
                "price_measure": price_measure,
                "priority": priority
            })
        
        # Sort by priority (lowest first)
        sorted_candidates = sorted(candidate_series, key=lambda x: x["priority"])
        
        if sorted_candidates:
            chosen = sorted_candidates[0]
            _LOGGER.debug(f"Selected TimeSeries with businessType: {chosen['business_type']}, "
                         f"curveType: {chosen['curve_type']}, priceMeasure: {chosen['price_measure']}")
            return chosen["element"]
        
        # Fallback to first element if no matches
        if time_series_elements:
            _LOGGER.warning("Could not identify optimal TimeSeries, falling back to first element")
            return time_series_elements[0]
            
        return None

    async def _process_data(self, data):
        """Process the data from ENTSO-E with correct XML namespace handling."""
        if not data:
            return None

        try:
            # The XML has a default namespace which must be handled explicitly
            # The Python xml.etree.ElementTree library requires all namespace prefixes to be included in paths
            # Define our namespace map - the key '' represents the default namespace
            nsmap = {
                "ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
            }

            # Parse XML
            root = ET.fromstring(data)

            # Find TimeSeries elements using explicit namespace
            time_series_elements = root.findall(".//ns:TimeSeries", nsmap)

            # Check if we found any TimeSeries elements
            if not time_series_elements:
                _LOGGER.error("No TimeSeries elements found in ENTSO-E response")
                _LOGGER.debug(f"First 500 chars of XML: {data[:500]}")
                return None

            # Select only the TimeSeries containing actual day-ahead prices
            price_time_series = self._identify_price_time_series(time_series_elements, nsmap)

            if not price_time_series:
                _LOGGER.error("Could not identify price TimeSeries element in ENTSO-E response")
                return None

            now = self._get_now()
            current_hour = now.hour
            hourly_prices = {}
            all_prices = []
            raw_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}

            use_cents = self.config.get("price_in_cents", False)

            # Extract any useful TimeSeries metadata
            currency = self._find_element_text(price_time_series, ".//ns:currency_Unit.name", nsmap) or "EUR"
            _LOGGER.debug(f"Currency from TimeSeries: {currency}")

            # Find Period elements with namespace
            period_elements = price_time_series.findall(".//ns:Period", nsmap)

            if not period_elements:
                _LOGGER.warning("No Period elements found in TimeSeries")
                return None

            for period in period_elements:
                # Extract timeInterval with proper namespace
                interval = period.find("ns:timeInterval", nsmap)
                if interval is None:
                    _LOGGER.warning("Missing timeInterval in Period")
                    continue

                # Get start and end times with proper namespace
                start_element = interval.find("ns:start", nsmap)
                end_element = interval.find("ns:end", nsmap)

                if start_element is None or end_element is None:
                    _LOGGER.warning("Missing start or end in timeInterval")
                    continue

                # Extract text content and convert to datetime
                start_text = start_element.text
                end_text = end_element.text

                try:
                    # Handle ISO format with Z timezone indicator
                    start_dt = datetime.datetime.fromisoformat(start_text.replace("Z", "+00:00"))
                    end_dt = datetime.datetime.fromisoformat(end_text.replace("Z", "+00:00"))
                    _LOGGER.debug(f"Period: {start_dt.isoformat()} to {end_dt.isoformat()}")
                except ValueError as e:
                    _LOGGER.error(f"Error parsing timeInterval: {e}")
                    continue

                # Extract resolution with proper namespace
                resolution_element = period.find("ns:resolution", nsmap)
                if resolution_element is None:
                    _LOGGER.warning("Missing resolution element in period, defaulting to hourly")
                    resolution = "PT60M"  # Default to hourly
                    resolution_minutes = 60
                else:
                    resolution = resolution_element.text
                    # Parse resolution format (e.g., PT15M means 15 minutes)
                    if resolution == "PT15M":
                        resolution_minutes = 15
                    elif resolution == "PT60M" or resolution == "PT1H":
                        resolution_minutes = 60
                    else:
                        _LOGGER.warning(f"Unknown resolution: {resolution}, defaulting to hourly")
                        resolution_minutes = 60

                _LOGGER.debug(f"Resolution: {resolution} ({resolution_minutes} minutes)")

                # Process Point elements
                points = period.findall("ns:Point", nsmap)
                if not points:
                    _LOGGER.warning("No Point elements found in Period")
                    continue

                # Build a dictionary of position -> price
                position_prices = {}
                for point in points:
                    position_element = point.find("ns:position", nsmap)
                    price_element = point.find("ns:price.amount", nsmap)

                    if position_element is None or price_element is None:
                        # Skip points with missing elements
                        continue

                    try:
                        position = int(position_element.text)
                        price = float(price_element.text)
                        position_prices[position] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Invalid position or price: {e}")
                        continue

                # Calculate total positions and verify we have data
                total_minutes = int((end_dt - start_dt).total_seconds() / 60)
                expected_positions = total_minutes // resolution_minutes

                _LOGGER.debug(f"Expected {expected_positions} positions, found {len(position_prices)}")

                # Process points for each position
                for position in range(1, expected_positions + 1):
                    if position not in position_prices:
                        continue

                    price = position_prices[position]

                    # Calculate the datetime for this position
                    position_minutes = (position - 1) * resolution_minutes
                    position_time = start_dt + datetime.timedelta(minutes=position_minutes)
                    position_end = position_time + datetime.timedelta(minutes=resolution_minutes)

                    # Convert to local time for comparison with current hour
                    local_position_time = self._convert_to_local(position_time)

                    # Store raw price data for API attributes
                    raw_prices.append({
                        "start": position_time.isoformat(),
                        "end": position_end.isoformat(),
                        "price": price
                    })

                    # Convert price from EUR/MWh to target currency/unit
                    # Fix: Use _convert_price without to_currency parameter
                    converted_price = await self._convert_price(
                        price=price,
                        from_currency=currency,
                        from_unit="MWh",
                        to_subunit=use_cents
                    )

                    all_prices.append(converted_price)

                    # Handle different resolutions
                    if resolution_minutes < 60:
                        # For sub-hourly data, aggregate to full hours
                        hour_start = local_position_time.replace(minute=0, second=0, microsecond=0)
                        hour_key = hour_start.strftime("%H:00")

                        if hour_key not in hourly_prices:
                            hourly_prices[hour_key] = {"sum": converted_price, "count": 1}
                        else:
                            hourly_prices[hour_key]["sum"] += converted_price
                            hourly_prices[hour_key]["count"] += 1
                    else:
                        # For hourly data, use directly
                        hour_key = local_position_time.strftime("%H:00")
                        hourly_prices[hour_key] = {"sum": converted_price, "count": 1}

                    # Check if this matches current hour
                    if local_position_time.hour == current_hour and local_position_time.date() == now.date():
                        # For sub-hourly data, this might happen multiple times per hour
                        # Store raw data for later averaging
                        if "current_hour" not in raw_values:
                            raw_values["current_hour"] = {"sum": price, "count": 1, "converted_sum": converted_price}
                        else:
                            raw_values["current_hour"]["sum"] += price
                            raw_values["current_hour"]["count"] += 1
                            raw_values["current_hour"]["converted_sum"] += converted_price

                    # Check if this is next hour
                    next_hour = (current_hour + 1) % 24
                    if local_position_time.hour == next_hour and local_position_time.date() == now.date():
                        # For sub-hourly data, store for later averaging
                        if "next_hour" not in raw_values:
                            raw_values["next_hour"] = {"sum": price, "count": 1, "converted_sum": converted_price}
                        else:
                            raw_values["next_hour"]["sum"] += price
                            raw_values["next_hour"]["count"] += 1
                            raw_values["next_hour"]["converted_sum"] += converted_price

            # Process final hourly prices
            final_hourly_prices = {}
            for hour_key, data in hourly_prices.items():
                final_hourly_prices[hour_key] = data["sum"] / data["count"]

            # Set current and next hour prices
            if "current_hour" in raw_values:
                current_hour_data = raw_values["current_hour"]
                current_price = current_hour_data["converted_sum"] / current_hour_data["count"]
                raw_values["current_price"] = {
                    "raw": current_hour_data["sum"] / current_hour_data["count"],
                    "converted": current_price,
                    "hour": current_hour
                }

            if "next_hour" in raw_values:
                next_hour_data = raw_values["next_hour"]
                next_hour_price = next_hour_data["converted_sum"] / next_hour_data["count"]
                raw_values["next_hour_price"] = {
                    "raw": next_hour_data["sum"] / next_hour_data["count"],
                    "converted": next_hour_price,
                    "hour": next_hour
                }

            # Calculate statistics
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
            peak_price = max(all_prices) if all_prices else None
            off_peak_price = min(all_prices) if all_prices else None

            # Store raw value details for statistics
            raw_values["day_average_price"] = {"value": day_average_price}
            raw_values["peak_price"] = {"value": peak_price}
            raw_values["off_peak_price"] = {"value": off_peak_price}

            # Ensure we have data for current hour
            if not current_price and final_hourly_prices:
                _LOGGER.warning(f"Current hour price not found, using first available hour")
                current_hour_str = f"{current_hour:02d}:00"
                if current_hour_str in final_hourly_prices:
                    current_price = final_hourly_prices[current_hour_str]
                else:
                    # Use first available price
                    first_hour = list(final_hourly_prices.keys())[0]
                    current_price = final_hourly_prices[first_hour]
                    _LOGGER.warning(f"Using {first_hour} price for current hour")

            # Ensure we have data for next hour
            if not next_hour_price and final_hourly_prices:
                next_hour_str = f"{next_hour:02d}:00"
                if next_hour_str in final_hourly_prices:
                    next_hour_price = final_hourly_prices[next_hour_str]
                    _LOGGER.debug(f"Found next hour price: {next_hour_price}")

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

    def _find_element_text(self, element, path, nsmap, default=None):
        """Helper method to safely extract text from an element."""
        child = element.find(path, nsmap)
        if child is not None:
            return child.text
        return default

    def _convert_to_local(self, dt):
        """Convert UTC datetime to local timezone."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)

        # If we have Home Assistant instance, use its timezone
        if hasattr(self, 'hass') and self.hass:
            from homeassistant.util import dt as dt_util
            return dt_util.as_local(dt)

        # Otherwise use system local time
        return dt.astimezone()

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

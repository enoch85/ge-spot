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

    BASE_URL = "https://transparency.entsoe.eu/api"

    async def _fetch_data(self):
        """Fetch data from ENTSO-E."""
        api_key = self.config.get(CONF_API_KEY) or self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            return None

        now = self._get_now()
        today = now
        tomorrow = today + datetime.timedelta(days=1)

        # Format dates for ENTSO-E API - one day period
        period_start = today.strftime("%Y%m%d0000")
        period_end = tomorrow.strftime("%Y%m%d0000")

        # Get area code - map our area code to ENTSO-E area code without default
        area = self.config.get("area")
        if not area:
            _LOGGER.error("No area provided in configuration")
            return None

        # Try to use the mapped ENTSOE code if available
        entsoe_area = ENTSOE_AREA_MAPPING.get(area, area)
        
        _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

        params = {
            "securityToken": api_key,
            "documentType": "A44",  # Day-ahead prices
            "in_Domain": entsoe_area,
            "out_Domain": entsoe_area,
            "periodStart": period_start,
            "periodEnd": period_end,
        }

        _LOGGER.debug(f"Fetching ENTSO-E with params: periodStart={period_start}, periodEnd={period_end}, area={entsoe_area}")

        # Use custom headers for ENTSO-E API
        headers = {
            "User-Agent": "HomeAssistantGESpot/1.0",
            "Accept": "application/xml;charset=UTF-8",
            "Content-Type": "application/xml;charset=UTF-8"
        }

        # Use the fetch_with_retry method with custom headers
        try:
            # Use a separate GET request with custom parameters since this API is picky
            await self._ensure_session()
            
            if not self.session or self.session.closed:
                _LOGGER.error("No valid session for ENTSO-E API request")
                return None
                
            url = self.BASE_URL
            
            response = None
            retries = 3
            
            for attempt in range(retries):
                try:
                    async with self.session.get(url, params=params, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            response = await resp.text()
                            break
                        elif resp.status == 403:
                            _LOGGER.error(f"ENTSO-E API authentication failed (403 Forbidden). Check your API key.")
                            # No need to retry on authentication failure
                            break
                        else:
                            error_text = await resp.text()
                            _LOGGER.error(f"ENTSO-E API request failed with status {resp.status}: {error_text[:200]}")
                            if attempt < retries - 1:
                                delay = 2 ** attempt
                                _LOGGER.debug(f"Retrying in {delay} seconds...")
                                await asyncio.sleep(delay)
                except Exception as e:
                    _LOGGER.error(f"Error during ENTSO-E API request (attempt {attempt+1}/{retries}): {e}")
                    if attempt < retries - 1:
                        delay = 2 ** attempt
                        await asyncio.sleep(delay)
            
            # Check for authentication errors in the response
            if response and "Not authorized" in response:
                _LOGGER.error(f"ENTSO-E API authentication failed: Not authorized. Check your API key.")
                return None
                
            return response
            
        except Exception as e:
            _LOGGER.error(f"Failed to fetch data from ENTSO-E: {e}")
            return None

    async def _process_data(self, data):
        """Process the data from ENTSO-E."""
        if not data:
            return None

        try:
            # Parse XML
            root = ET.fromstring(data)
            ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"}

            # Find TimeSeries elements
            time_series = root.findall(".//ns:TimeSeries", ns)

            now = self._get_now()
            current_hour = now.hour

            hourly_prices = {}
            all_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}
            raw_prices = []

            use_cents = self.config.get("price_in_cents", False)

            for ts in time_series:
                # Find Point elements with price data
                points = ts.findall(".//ns:Point", ns)

                for point in points:
                    position = int(point.find("ns:position", ns).text)
                    price = float(point.find("ns:price.amount", ns).text)

                    # Store raw price data
                    start_hour = (position - 1)
                    start_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                    end_time = start_time + datetime.timedelta(hours=1)

                    raw_prices.append({
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "price": price
                    })

                    # Convert from EUR/MWh to the appropriate currency/unit
                    converted_price = await self._convert_price(
                        price=price,
                        from_unit="MWh",
                        to_unit="kWh",
                        from_currency="EUR",
                        to_currency=self._currency,
                        to_subunit=use_cents
                    )

                    # Calculate the hour based on position (1-24)
                    hour = (position - 1)
                    hour_str = f"{hour:02d}:00"

                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)

                    if hour == current_hour:
                        current_price = converted_price
                        raw_values["current_price"] = {
                            "raw": price,
                            "converted": converted_price,
                            "hour": hour
                        }

                    if hour == (current_hour + 1) % 24:
                        next_hour_price = converted_price
                        raw_values["next_hour_price"] = {
                            "raw": price,
                            "converted": converted_price,
                            "hour": (current_hour + 1) % 24
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
                "hourly_prices": hourly_prices,
                "raw_prices": raw_prices,
                "raw_values": raw_values,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "api_key_valid": True  # Indicate that the API key is valid
            }

        except ET.ParseError as e:
            _LOGGER.error(f"Error parsing ENTSO-E XML: {e}")
            return None
        except Exception as e:
            _LOGGER.error(f"Error processing ENTSO-E data: {e}")
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
            result = await api._fetch_data()

            # Close session if we created one
            if api._owns_session:
                await api.close()

            # Check if we got a valid response
            if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
                return True
            elif isinstance(result, str) and "Not authorized" in result:
                _LOGGER.error("API key validation failed: Not authorized")
                return False
            else:
                _LOGGER.error("API key validation failed: No data returned")
                return False

        except Exception as e:
            _LOGGER.error(f"API key validation error: {e}")
            return False

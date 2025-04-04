import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, convert_energy_price
from ..const import ENTSOE_AREA_MAPPING

_LOGGER = logging.getLogger(__name__)

class EntsoEAPI(BaseEnergyAPI):
    """API handler for ENTSO-E Transparency Platform."""

    BASE_URL = "https://transparency.entsoe.eu/api"

    async def _fetch_data(self):
        """Fetch data from ENTSO-E."""
        api_key = self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            return None

        now = self._get_now()
        today = now
        tomorrow = today + datetime.timedelta(days=1)

        # Format dates for ENTSO-E API
        period_start = today.strftime("%Y%m%d0000")
        period_end = tomorrow.strftime("%Y%m%d0000")

        # Get area code - map our area code to ENTSO-E area code without default
        area = self.config.get("area")
        if not area:
            _LOGGER.error("No area provided in configuration")
            return None
            
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

        _LOGGER.debug(f"Fetching ENTSO-E with params: {params}")

        # Use the fetch_with_retry method from BaseEnergyAPI
        return await self._fetch_with_retry(self.BASE_URL, params=params)

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

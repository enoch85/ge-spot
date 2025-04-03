import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, convert_energy_price

_LOGGER = logging.getLogger(__name__)

class EntsoEAPI(BaseEnergyAPI):
    """API handler for ENTSO-E Transparency Platform."""
    
    BASE_URL = "https://transparency.entsoe.eu/api"
    
    async def _fetch_data(self):
        """Fetch data from ENTSO-E."""
        api_key = self.config.get("api_key")
        if not api_key:
            _LOGGER.error("API key is required for ENTSO-E")
            return None
            
        now = self._get_now()
        today = now
        tomorrow = today + datetime.timedelta(days=1)
        
        # Format dates for ENTSO-E API
        period_start = today.strftime("%Y%m%d0000")
        period_end = tomorrow.strftime("%Y%m%d0000")
        
        # Default to Germany-Luxembourg bidding zone
        area = self.config.get("area", "10Y1001A1001A63L")
        
        params = {
            "securityToken": api_key,
            "documentType": "A44",  # Day-ahead prices
            "in_Domain": area,
            "out_Domain": area,
            "periodStart": period_start,
            "periodEnd": period_end,
        }
        
        _LOGGER.debug(f"Fetching ENTSO-E with params: {params}")
        
        url = self.BASE_URL
        
        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from ENTSO-E (attempt {attempt+1}/{retry_count}): {response.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                        
                    return await response.text()
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from ENTSO-E (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from ENTSO-E (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
                
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
            
            use_cents = self.config.get("price_in_cents", False)
            
            for ts in time_series:
                # Find Point elements with price data
                points = ts.findall(".//ns:Point", ns)
                
                for point in points:
                    position = int(point.find("ns:position", ns).text)
                    price = float(point.find("ns:price.amount", ns).text)
                    
                    # Convert from EUR/MWh to the appropriate currency/unit
                    price = convert_energy_price(price, from_unit="MWh", to_unit="kWh", vat=0)
                    price = self._apply_vat(price)
                    
                    # Convert to subunit if needed
                    if use_cents:
                        price = convert_to_subunit(price, self._currency)
                    
                    # Calculate the hour based on position (1-24)
                    hour = (position - 1)
                    hour_str = f"{hour:02d}:00"
                    
                    hourly_prices[hour_str] = price
                    all_prices.append(price)
                    
                    if hour == current_hour:
                        current_price = price
                        
                    if hour == (current_hour + 1) % 24:
                        next_hour_price = price
            
            # Calculate day average
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
            
            # Find peak and off-peak prices
            peak_price = max(all_prices) if all_prices else None
            off_peak_price = min(all_prices) if all_prices else None
            
            return {
                "current_price": current_price,
                "next_hour_price": next_hour_price,
                "day_average_price": day_average_price,
                "peak_price": peak_price,
                "off_peak_price": off_peak_price,
                "hourly_prices": hourly_prices,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            
        except ET.ParseError as e:
            _LOGGER.error(f"Error parsing ENTSO-E XML: {e}")
            return None
        except Exception as e:
            _LOGGER.error(f"Error processing ENTSO-E data: {e}")
            return None

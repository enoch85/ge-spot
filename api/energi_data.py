import logging
import datetime
import json
import asyncio
from .base import BaseEnergyAPI

_LOGGER = logging.getLogger(__name__)

class EnergiDataServiceAPI(BaseEnergyAPI):
    """API handler for Energi Data Service."""
    
    BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"
    
    async def _fetch_data(self):
        """Fetch data from Energi Data Service."""
        now = self._get_now()
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        area = self.config.get("area", "DK1")  # Default to Western Denmark
        
        params = {
            "start": f"{today}T00:00",
            "end": f"{tomorrow}T00:00",
            "filter": json.dumps({"PriceArea": area}),
            "sort": "HourDK",
            "timezone": "dk",
        }
        
        _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")
        
        url = self.BASE_URL
        
        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from Energi Data Service (attempt {attempt+1}/{retry_count}): {response.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                        
                    return await response.json()
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from Energi Data Service (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from Energi Data Service (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
                
        return None
            
    def _process_data(self, data):
        """Process the data from Energi Data Service."""
        if not data or "records" not in data or not data["records"]:
            return None
            
        records = data["records"]
        now = self._get_now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Find current price
        current_price = None
        next_hour_price = None
        hourly_prices = {}
        all_prices = []
        
        for record in records:
            hour_dk = datetime.datetime.fromisoformat(record["HourDK"].replace("Z", "+00:00"))
            price = record["SpotPriceDKK"] / 1000  # Convert from DKK/MWh to DKK/kWh
            price = self._apply_vat(price)
            all_prices.append(price)
            
            # Store in hourly prices
            hour_str = hour_dk.strftime("%H:%M")
            hourly_prices[hour_str] = price
            
            # Check if this is current hour
            if hour_dk.hour == current_hour.hour and hour_dk.day == current_hour.day:
                current_price = price
                
            # Check if this is next hour
            next_hour = current_hour + datetime.timedelta(hours=1)
            if hour_dk.hour == next_hour.hour and hour_dk.day == next_hour.day:
                next_hour_price = price
        
        # Calculate day average
        day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
        
        # Find peak (highest) and off-peak (lowest) prices
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

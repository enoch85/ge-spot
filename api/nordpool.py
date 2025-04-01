import logging
import datetime
import asyncio
from .base import BaseEnergyAPI

_LOGGER = logging.getLogger(__name__)

class NordpoolAPI(BaseEnergyAPI):
    """API handler for Nordpool."""
    
    BASE_URL = "https://www.nordpoolgroup.com/api/marketdata/page/10"
    
    async def _fetch_data(self):
        """Fetch data from Nordpool."""
        now = self._get_now()
        today = now.strftime("%d-%m-%Y")
        
        area = self.config.get("area", "Oslo")  # Default to Oslo
        currency = "EUR"  # Default currency for the API request
        
        params = {
            "currency": currency,
            "endDate": today,
        }
        
        _LOGGER.debug(f"Fetching Nordpool with params: {params}")
        
        url = self.BASE_URL
        
        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from Nordpool (attempt {attempt+1}/{retry_count}): {response.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                        
                    return await response.json()
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from Nordpool (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from Nordpool (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
                
        return None
            
    def _process_data(self, data):
        """Process the data from Nordpool."""
        if not data or "data" not in data or "Rows" not in data["data"]:
            return None
            
        rows = data["data"]["Rows"]
        area = self.config.get("area", "Oslo")
        
        now = self._get_now()
        current_hour = now.hour
        
        # Find current price
        current_price = None
        next_hour_price = None
        hourly_prices = {}
        all_prices = []
        
        for row in rows:
            # Check if this is a price row (not a header)
            if "IsExtraRow" in row and not row["IsExtraRow"]:
                start_time = row.get("StartTime")
                if not start_time:
                    continue
                    
                # Parse the hour from the name
                hour_match = None
                name = row.get("Name", "")
                for i in range(24):
                    if f"{i:02d}-" in name:
                        hour_match = i
                        break
                        
                if hour_match is None:
                    continue
                    
                # Find the price for the specified area
                for column in row["Columns"]:
                    if area in column.get("Name", ""):
                        price_str = column.get("Value", "").replace(" ", "").replace(",", ".")
                        try:
                            # Convert from currency/MWh to currency/kWh
                            price = float(price_str) / 1000
                            price = self._apply_vat(price)
                            
                            all_prices.append(price)
                            
                            # Store in hourly prices
                            hour_str = f"{hour_match:02d}:00"
                            hourly_prices[hour_str] = price
                            
                            # Check if this is current hour
                            if hour_match == current_hour:
                                current_price = price
                                
                            # Check if this is next hour
                            if hour_match == (current_hour + 1) % 24:
                                next_hour_price = price
                                
                        except (ValueError, TypeError):
                            continue
        
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
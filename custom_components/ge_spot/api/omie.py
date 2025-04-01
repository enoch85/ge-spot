import logging
import datetime
import asyncio
import csv
import io
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, convert_energy_price

_LOGGER = logging.getLogger(__name__)

class OmieAPI(BaseEnergyAPI):
    """API handler for OMIE (Iberian Market)."""
    
    BASE_URL = "https://www.omie.es/en/file-download"
    
    async def _fetch_data(self):
        """Fetch data from OMIE."""
        now = self._get_now()
        
        # Format date for OMIE API
        year = now.year
        month = now.month
        day = now.day
        
        params = {
            "parents[0]": "marginalpdbc",
            "filename": f"marginalpdbc_{year}_{month:02d}_{day:02d}.1",
        }
        
        _LOGGER.debug(f"Fetching OMIE with params: {params}")
        
        url = self.BASE_URL
        
        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from OMIE (attempt {attempt+1}/{retry_count}): {response.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                        
                    return await response.text()
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from OMIE (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from OMIE (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
                
        return None
            
    def _process_data(self, data):
        """Process the data from OMIE."""
        if not data:
            return None
            
        try:
            # Parse CSV-like data from OMIE
            reader = csv.reader(io.StringIO(data), delimiter=';')
            
            # Skip header rows (OMIE format has multiple header rows)
            rows = list(reader)
            
            # Find the data rows - OMIE format varies, so we need to find the actual data
            data_rows = []
            for row in rows:
                # Look for rows with hour and price data
                if len(row) >= 3 and row[0].isdigit():
                    data_rows.append(row)
            
            if not data_rows:
                _LOGGER.error("No valid data rows found in OMIE response")
                return None
            
            now = self._get_now()
            current_hour = now.hour
            
            hourly_prices = {}
            all_prices = []
            current_price = None
            next_hour_price = None
            
            area = self.config.get("area", "ES")  # Default to Spain
            area_index = 1 if area == "ES" else 2  # Spain is column 1, Portugal is column 2
            use_cents = self.config.get("price_in_cents", False)
            
            for row in data_rows:
                try:
                    hour = int(row[0]) - 1  # OMIE hours are 1-24
                    price_str = row[area_index].replace(",", ".")
                    
                    # Convert from EUR/MWh to EUR/kWh with utility function
                    price = convert_energy_price(float(price_str), from_unit="MWh", to_unit="kWh", vat=0)
                    price = self._apply_vat(price)
                    
                    # Convert to cents if needed
                    if use_cents:
                        price = convert_to_subunit(price, self._currency)
                    
                    hour_str = f"{hour:02d}:00"
                    hourly_prices[hour_str] = price
                    all_prices.append(price)
                    
                    if hour == current_hour:
                        current_price = price
                        
                    if hour == (current_hour + 1) % 24:
                        next_hour_price = price
                        
                except (ValueError, IndexError) as e:
                    _LOGGER.warning(f"Error parsing OMIE row {row}: {e}")
                    continue
            
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
            
        except Exception as e:
            _LOGGER.error(f"Error processing OMIE data: {e}")
            return None

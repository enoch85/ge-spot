import logging
import datetime
import asyncio
from .base import BaseEnergyAPI

_LOGGER = logging.getLogger(__name__)

class NordpoolAPI(BaseEnergyAPI):
    """API handler for Nordpool using the updated API endpoint."""
    
    # New API endpoint based on the updated Nordpool API
    BASE_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
    
    async def _fetch_data(self):
        """Fetch data from Nordpool."""
        try:
            now = self._get_now()
            today = now.strftime("%Y-%m-%d")
            tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            
            area = self.config.get("area", "Oslo")  # Default to Oslo
            currency = "EUR"  # Default currency for the API request
            
            # Map the area names to the API's delivery area codes if needed
            area_mapping = {
                "Oslo": "Oslo",
                "Kr.sand": "Kr.sand",
                "Bergen": "Bergen",
                "Molde": "Molde",
                "Tr.heim": "Tr.heim",
                "Tromsø": "Tromsø",
                "SE1": "SE1",
                "SE2": "SE2",
                "SE3": "SE3",
                "SE4": "SE4",
                "DK1": "DK1",
                "DK2": "DK2",
                "FI": "FI",
                "EE": "EE",
                "LV": "LV",
                "LT": "LT",
            }
            
            delivery_area = area_mapping.get(area, area)
            
            # Fetch today's data
            today_data = await self._fetch_day_data(delivery_area, currency, today)
            
            # Fetch tomorrow's data if available (after 13:00 CET)
            tomorrow_data = None
            # Convert now to CET timezone for checking if tomorrow's prices should be available
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_cet = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=1)))  # CET is UTC+1
            
            # If it's after 13:00 CET, tomorrow's prices should be available
            if now_cet.hour >= 13:
                tomorrow_data = await self._fetch_day_data(delivery_area, currency, tomorrow)
            
            # Only return data structure if we actually have today's data
            if today_data is not None:
                return {
                    "today": today_data,
                    "tomorrow": tomorrow_data,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            
            # Otherwise return None to trigger fallback
            _LOGGER.warning("No valid data returned from Nordpool API for today")
            return None
            
        except Exception as e:
            _LOGGER.error(f"Error in _fetch_data: {str(e)}")
            return None
    
    async def _fetch_day_data(self, delivery_area, currency, date):
        """Fetch data for a specific day."""
        if not delivery_area or not currency or not date:
            _LOGGER.error("Missing required parameters for Nordpool API call")
            return None
            
        params = {
            "currency": currency,
            "date": date,
            "market": "DayAhead",
            "deliveryArea": delivery_area
        }
        
        _LOGGER.debug(f"Fetching Nordpool with params: {params}")
        
        url = self.BASE_URL
        
        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                _LOGGER.debug(f"Sending request to Nordpool: {url} with params: {params}")
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from Nordpool (attempt {attempt+1}/{retry_count}): Status {response.status}")
                        
                        # Try to get the error response body for better debugging
                        try:
                            error_text = await response.text()
                            _LOGGER.error(f"Nordpool error response: {error_text[:500]}...")
                        except Exception as e:
                            _LOGGER.error(f"Could not read error response from Nordpool: {str(e)}")
                            
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                    
                    _LOGGER.debug("Successfully received response from Nordpool API")
                    
                    try:
                        data = await response.json()
                    except Exception as e:
                        _LOGGER.error(f"Error parsing JSON from Nordpool: {str(e)}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    # Basic validation of the returned data
                    if not data:
                        _LOGGER.error("Empty data returned from Nordpool API")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                        
                    if not isinstance(data, dict):
                        _LOGGER.error(f"Invalid data format from Nordpool: {type(data)}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                        
                    return data
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from Nordpool (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None
            except Exception as e:
                _LOGGER.error(f"Error fetching from Nordpool (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None
                
        return None
    
    async def async_get_data(self):
        """Get data with fallback to simulation if real data fails."""
        try:
            # Try to get real data
            raw_data = await self._fetch_data()
            if raw_data:
                try:
                    data = self._process_data(raw_data)
                    if data:
                        return data
                except AttributeError as e:
                    _LOGGER.error(f"AttributeError in Nordpool data processing: {str(e)}, falling back to simulation")
                    return self._generate_simulated_data()
                except Exception as e:
                    _LOGGER.error(f"Error processing Nordpool data: {str(e)}, falling back to simulation")
                    return self._generate_simulated_data()
                
            # If real data fails, use simulated data
            _LOGGER.warning("Failed to get real data from Nordpool, using simulated data")
            return self._generate_simulated_data()
        except AttributeError as e:
            _LOGGER.error(f"AttributeError in Nordpool data processing: {str(e)}, falling back to simulation")
            return self._generate_simulated_data()
        except Exception as e:
            _LOGGER.error(f"Error getting Nordpool data: {e}, falling back to simulation")
            return self._generate_simulated_data()
            
    def _process_data(self, raw_data):
        """Process the data from Nordpool."""
        if not raw_data:
            _LOGGER.error("No data in Nordpool response")
            return None
            
        today_data = raw_data.get("today")
        if not today_data:
            _LOGGER.error("Missing today data in Nordpool response")
            return None
            
        tomorrow_data = raw_data.get("tomorrow")
        timestamp = raw_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
        
        if "multiAreaEntries" not in today_data:
            _LOGGER.error("Missing multiAreaEntries in Nordpool today data")
            return None
            
        area = self.config.get("area", "Oslo")  # Default to Oslo
        now = self._get_now()
        current_hour = now.hour
        
        result = {
            "last_updated": timestamp,
        }
        
        # Process today's data
        try:
            today_processed = self._process_day_data(today_data, area, current_hour)
            if today_processed:
                # Add today's data to result
                result.update({
                    "current_price": today_processed.get("current_price"),
                    "next_hour_price": today_processed.get("next_hour_price"),
                    "day_average_price": today_processed.get("day_average_price"),
                    "peak_price": today_processed.get("peak_price"),
                    "off_peak_price": today_processed.get("off_peak_price"),
                    "hourly_prices": today_processed.get("hourly_prices", {}),
                })
            else:
                _LOGGER.error("Failed to process today's Nordpool data")
                return None
        except Exception as e:
            _LOGGER.error(f"Error processing today's Nordpool data: {str(e)}")
            return None
        
        # Process tomorrow's data if available
        if tomorrow_data and "multiAreaEntries" in tomorrow_data:
            try:
                tomorrow_processed = self._process_day_data(tomorrow_data, area)
                if tomorrow_processed:
                    # Add tomorrow's data to result
                    result.update({
                        "tomorrow_average_price": tomorrow_processed.get("day_average_price"),
                        "tomorrow_peak_price": tomorrow_processed.get("peak_price"),
                        "tomorrow_off_peak_price": tomorrow_processed.get("off_peak_price"),
                        "tomorrow_hourly_prices": tomorrow_processed.get("hourly_prices", {}),
                    })
            except Exception as e:
                _LOGGER.warning(f"Error processing tomorrow's Nordpool data: {str(e)}")
                # Continue even if tomorrow's data fails
        
        return result
    
    def _process_day_data(self, data, area, current_hour=None):
        """Process price data for a single day."""
        if not data:
            _LOGGER.debug("No data provided to _process_day_data")
            return None
            
        if "multiAreaEntries" not in data:
            _LOGGER.debug("No multiAreaEntries in data for _process_day_data")
            return None
            
        # Process today's prices
        current_price = None
        next_hour_price = None
        hourly_prices = {}
        all_prices = []
        
        try:
            # Process based on the new API format
            entries = data.get("multiAreaEntries", [])
            if not entries:
                _LOGGER.debug("Empty multiAreaEntries in Nordpool data")
                return None
                
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                    
                start_time = entry.get("deliveryStart")
                if not start_time:
                    continue
                
                entry_per_area = entry.get("entryPerArea")
                if not entry_per_area or not isinstance(entry_per_area, dict):
                    continue
                
                # Check if this area exists in the entryPerArea data
                if area not in entry_per_area:
                    continue
                
                # Get the price for this area
                price = entry_per_area.get(area)
                if price is None:
                    continue
                
                # Convert to float if needed
                if isinstance(price, str):
                    try:
                        price = float(price.replace(",", ".").replace(" ", ""))
                    except ValueError:
                        continue
                elif not isinstance(price, (int, float)):
                    continue
                
                # Convert from EUR/MWh to EUR/kWh
                price = price / 1000
                price = self._apply_vat(price)
                
                # Parse the hour from the start_time
                try:
                    dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    local_dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                    hour = local_dt.hour
                    
                    # Format time in ISO format (HH:MM:SS)
                    hour_str = f"{hour:02d}:00:00"
                    hourly_prices[hour_str] = price
                    all_prices.append(price)
                    
                    # Check if this is current hour
                    if current_hour is not None and hour == current_hour:
                        current_price = price
                        
                    # Check if this is next hour
                    if current_hour is not None and hour == (current_hour + 1) % 24:
                        next_hour_price = price
                        
                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"Error parsing datetime {start_time}: {e}")
                    continue
            
            if not hourly_prices:
                _LOGGER.warning("No hourly prices found in Nordpool data")
                return None
                
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
            }
        except Exception as e:
            _LOGGER.error(f"Error processing Nordpool data: {e}")
            return None
        
    def _generate_simulated_data(self):
        """Generate simulated data when Nordpool API is unavailable."""
        now = self._get_now()
        current_hour = now.hour
        
        # Create simulated hourly prices for today
        today_hourly_prices = {}
        today_all_prices = []
        
        # Create simulated hourly prices for tomorrow
        tomorrow_hourly_prices = {}
        tomorrow_all_prices = []
        
        # Generate prices with realistic patterns for today and tomorrow
        for hour in range(24):
            # Base price with time-based variation
            is_peak = (7 <= hour <= 9) or (18 <= hour <= 21)
            
            # Today's prices
            if is_peak:
                today_price = 0.18 + 0.02 * (hour % 3) + (now.day % 10) * 0.001
            else:
                today_price = 0.12 + 0.01 * (abs(12 - hour) / 12) + (now.day % 10) * 0.001
            
            today_price = self._apply_vat(today_price)
            hour_str = f"{hour:02d}:00:00"  # ISO format HH:MM:SS
            today_hourly_prices[hour_str] = today_price
            today_all_prices.append(today_price)
            
            # Tomorrow's prices (slightly different pattern)
            if is_peak:
                tomorrow_price = 0.19 + 0.015 * (hour % 3) + ((now.day + 1) % 10) * 0.001
            else:
                tomorrow_price = 0.13 + 0.008 * (abs(12 - hour) / 12) + ((now.day + 1) % 10) * 0.001
            
            tomorrow_price = self._apply_vat(tomorrow_price)
            tomorrow_hourly_prices[hour_str] = tomorrow_price
            tomorrow_all_prices.append(tomorrow_price)
        
        current_price = today_hourly_prices.get(f"{current_hour:02d}:00:00")
        next_hour_price = today_hourly_prices.get(f"{(current_hour + 1) % 24:02d}:00:00")
        
        # Calculate day averages
        today_average_price = sum(today_all_prices) / len(today_all_prices) if today_all_prices else None
        tomorrow_average_price = sum(tomorrow_all_prices) / len(tomorrow_all_prices) if tomorrow_all_prices else None
        
        # Find peak and off-peak prices
        today_peak_price = max(today_all_prices) if today_all_prices else None
        today_off_peak_price = min(today_all_prices) if today_all_prices else None
        
        tomorrow_peak_price = max(tomorrow_all_prices) if tomorrow_all_prices else None
        tomorrow_off_peak_price = min(tomorrow_all_prices) if tomorrow_all_prices else None
        
        return {
            "current_price": current_price,
            "next_hour_price": next_hour_price,
            "day_average_price": today_average_price,
            "peak_price": today_peak_price,
            "off_peak_price": today_off_peak_price,
            "hourly_prices": today_hourly_prices,
            "tomorrow_average_price": tomorrow_average_price,
            "tomorrow_peak_price": tomorrow_peak_price,
            "tomorrow_off_peak_price": tomorrow_off_peak_price,
            "tomorrow_hourly_prices": tomorrow_hourly_prices,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "simulated": True,  # Flag to indicate this is simulated data
        }

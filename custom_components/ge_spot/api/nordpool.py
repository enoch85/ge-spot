"""API module for Nordpool."""
import logging
import datetime
import asyncio
from .base import BaseEnergyAPI
from ..utils.currency_utils import convert_to_subunit, convert_energy_price
from .nordpool_utils import process_day_data, generate_simulated_data

# Import constants directly from the module
from custom_components.ge_spot.const import (
    AREA_TIMEZONES, 
    REGION_TO_CURRENCY, 
    CONF_DISPLAY_UNIT, 
    DISPLAY_UNIT_CENTS,
    CURRENCY_SUBUNIT_NAMES,
    NORDPOOL_DELIVERY_AREA_MAPPING,
)

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
            # Override currency if needed for this area
            specific_currency = REGION_TO_CURRENCY.get(area)
            if specific_currency:
                self._currency = specific_currency
                _LOGGER.debug(f"Using area-specific currency for {area}: {self._currency}")
            else:
                _LOGGER.debug(f"No specific currency found for area {area}, using default: {self._currency}")
                
            # Set price_in_cents based on display unit configuration
            if self.config.get(CONF_DISPLAY_UNIT) == DISPLAY_UNIT_CENTS:
                self.config["price_in_cents"] = True
                _LOGGER.debug(f"Using subunit display (price_in_cents=True) for currency: {self._currency} - {CURRENCY_SUBUNIT_NAMES.get(self._currency, 'cents')}")
            
            currency = "EUR"  # Default currency for the API request
            
            # Map the area names to the API's delivery area codes
            delivery_area = NORDPOOL_DELIVERY_AREA_MAPPING.get(area, area)
            _LOGGER.debug(f"Fetching Nordpool data for area: {delivery_area}")
            
            # Fetch today's data
            params = {
                "currency": currency,
                "date": today,
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }
            _LOGGER.debug(f"Fetching today's data with params: {params}")
            today_data = await self._fetch_with_retry(self.BASE_URL, params=params)
            
            if today_data is None:
                _LOGGER.error(f"Failed to fetch today's data for {delivery_area}")
                return None
                
            # Log the structure of the data received to help with debugging
            if today_data and "multiAreaEntries" in today_data:
                _LOGGER.debug(f"Successfully retrieved today's data with {len(today_data['multiAreaEntries'])} entries")
            else:
                _LOGGER.error(f"Unexpected today's data structure: {today_data.keys() if today_data else 'None'}")
            
            # Fetch tomorrow's data if available (after 13:00 CET)
            tomorrow_data = None
            # Convert now to CET timezone for checking if tomorrow's prices should be available
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_cet = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=1)))  # CET is UTC+1
            
            # If it's after 13:00 CET, tomorrow's prices should be available
            if now_cet.hour >= 13:
                params["date"] = tomorrow
                _LOGGER.debug(f"Fetching tomorrow's data with params: {params}")
                tomorrow_data = await self._fetch_with_retry(self.BASE_URL, params=params)
                
                if tomorrow_data and "multiAreaEntries" in tomorrow_data:
                    _LOGGER.debug(f"Successfully retrieved tomorrow's data with {len(tomorrow_data['multiAreaEntries'])} entries")
                else:
                    _LOGGER.warning(f"Tomorrow's data not available or has unexpected structure: {tomorrow_data.keys() if tomorrow_data else 'None'}")
            else:
                _LOGGER.debug(f"Not fetching tomorrow's data yet, current CET hour: {now_cet.hour}")
            
            # Only return data structure if we actually have today's data
            if today_data is not None:
                return {
                    "today": today_data,
                    "tomorrow": tomorrow_data,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            
            return None
            
        except Exception as e:
            _LOGGER.error(f"Error in _fetch_data: {str(e)}")
            return None
            
    def _process_data(self, raw_data):
        """Process the data from Nordpool."""
        if not raw_data:
            _LOGGER.error("No data in Nordpool response")
            return self._generate_simulated_data()
            
        today_data = raw_data.get("today")
        if not today_data:
            _LOGGER.error("Missing today data in Nordpool response")
            return self._generate_simulated_data()
            
        tomorrow_data = raw_data.get("tomorrow")
        timestamp = raw_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
        
        if "multiAreaEntries" not in today_data:
            _LOGGER.error("Missing multiAreaEntries in Nordpool today data")
            return self._generate_simulated_data()
            
        area = self.config.get("area", "Oslo")  # Default to Oslo
        now = self._get_now()
        current_hour = now.hour
        
        result = {
            "last_updated": timestamp,
        }
        
        # Process today's data
        try:
            _LOGGER.debug(f"Processing today's data for area: {area}")
            today_processed = process_day_data(today_data, area, current_hour, 
                                              self.config.get("price_in_cents", False), 
                                              self._currency, self._apply_vat)
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
                _LOGGER.debug(f"Successfully processed today's data, current price: {today_processed.get('current_price')}")
            else:
                _LOGGER.error("Failed to process today's Nordpool data, using simulated data")
                return self._generate_simulated_data()
        except Exception as e:
            _LOGGER.error(f"Error processing today's Nordpool data: {str(e)}")
            return self._generate_simulated_data()
        
        # Process tomorrow's data if available
        if tomorrow_data and "multiAreaEntries" in tomorrow_data:
            try:
                _LOGGER.debug(f"Processing tomorrow's data for area: {area}")
                tomorrow_processed = process_day_data(tomorrow_data, area, None,
                                                    self.config.get("price_in_cents", False),
                                                    self._currency, self._apply_vat)
                if tomorrow_processed:
                    # Add tomorrow's data to result
                    result.update({
                        "tomorrow_average_price": tomorrow_processed.get("day_average_price"),
                        "tomorrow_peak_price": tomorrow_processed.get("peak_price"),
                        "tomorrow_off_peak_price": tomorrow_processed.get("off_peak_price"),
                        "tomorrow_hourly_prices": tomorrow_processed.get("hourly_prices", {}),
                    })
                    _LOGGER.debug("Successfully processed tomorrow's data")
                else:
                    _LOGGER.warning("Failed to process tomorrow's Nordpool data")
            except Exception as e:
                _LOGGER.warning(f"Error processing tomorrow's Nordpool data: {str(e)}")
                # Continue even if tomorrow's data fails
        
        return result
        
    def _generate_simulated_data(self):
        """Generate simulated data when Nordpool API is unavailable."""
        _LOGGER.warning(f"Generating simulated data for area: {self.config.get('area')}")
        return generate_simulated_data(self._get_now(), self._apply_vat, self._currency, 
                                      self.config.get("price_in_cents", False))

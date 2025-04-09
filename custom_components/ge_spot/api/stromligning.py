"""API handler for Stromligning.dk."""
import logging
import datetime
from typing import Dict, Any, Optional

from .base import BaseEnergyAPI
from ..const import (
    Config,
    DisplayUnit,
    Currency,
    EnergyUnit
)
from ..timezone import ensure_timezone_aware

_LOGGER = logging.getLogger(__name__)

class StromligningConstants:
    """Constants for Stromligning.dk API."""
    BASE_URL = "https://stromligning.dk/api/prices"
    DEFAULT_AREA = "DK1"
    DEFAULT_CURRENCY = "DKK"
    PRICE_COMPONENTS = {
        "ELECTRICITY": "electricity",
        "GRID": "grid",
        "TAX": "tax"
    }

class StromligningAPI(BaseEnergyAPI):
    """API handler for Stromligning.dk."""

    BASE_URL = StromligningConstants.BASE_URL
    
    async def _fetch_data(self):
        """Fetch data from Stromligning.dk API."""
        now = self._get_now()
        today = now.date()
        tomorrow = today + datetime.timedelta(days=1)
        yesterday = today - datetime.timedelta(days=1)
        
        # Format dates for API query
        from_date = yesterday.isoformat() + "T00:00:00"
        to_date = tomorrow.isoformat() + "T23:59:59"
        
        # Get area code - use the configured area (typically DK1 or DK2)
        area = self.config.get("area", StromligningConstants.DEFAULT_AREA)
        
        params = {
            "from": from_date,
            "to": to_date,
            "priceArea": area,
            "lean": "false"  # We want the detailed response
        }
        
        _LOGGER.debug(f"Fetching Stromligning with params: {params}")
        
        response = await self.data_fetcher.fetch_with_retry(self.BASE_URL, params=params)
        return response

    async def _process_data(self, data):
        """Process the data from Stromligning.dk."""
        if not data or "prices" not in data or not data["prices"]:
            _LOGGER.error("No valid data received from Stromligning API")
            return None
        
        try:
            # Extract price area
            price_area = data.get("priceArea", self.config.get("area"))
            
            # Process all hourly prices
            hourly_prices = {}
            all_prices = []
            raw_prices = []
            
            now = self._get_now()
            current_hour = now.hour
            raw_values = {}
            
            for price_entry in data["prices"]:
                # Extract timestamp and price
                if "date" not in price_entry or "price" not in price_entry:
                    continue
                
                try:
                    # Parse timestamp
                    timestamp_str = price_entry["date"]
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1] + "+00:00"
                    
                    timestamp = datetime.datetime.fromisoformat(timestamp_str)
                    timestamp = ensure_timezone_aware(timestamp)
                    
                    # Convert to local time
                    if hasattr(self, 'hass') and self.hass:
                        from homeassistant.util import dt as dt_util
                        local_dt = dt_util.as_local(timestamp)
                    else:
                        local_dt = timestamp.astimezone()
                    
                    # Extract price value (DKK/kWh with VAT)
                    total_price = price_entry["price"]["total"]
                    
                    # For logging and diagnostics, extract the price components
                    electricity_price = price_entry["details"]["electricity"]["total"]
                    grid_price = (
                        price_entry["details"]["transmission"]["systemTariff"]["total"] + 
                        price_entry["details"]["transmission"]["netTariff"]["total"] +
                        price_entry["details"]["distribution"]["total"]
                    )
                    tax_price = price_entry["details"]["electricityTax"]["total"]
                    
                    # Store raw price data
                    raw_prices.append({
                        "start": local_dt.isoformat(),
                        "end": (local_dt + datetime.timedelta(hours=1)).isoformat(),
                        "price": total_price,
                        "components": {
                            StromligningConstants.PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                            StromligningConstants.PRICE_COMPONENTS["GRID"]: grid_price,
                            StromligningConstants.PRICE_COMPONENTS["TAX"]: tax_price
                        }
                    })
                    
                    # Use centralized conversion method
                    # Note: Stromligning returns prices in DKK/kWh already, so we only need to convert currency if needed
                    converted_price = await self._convert_price(
                        price=total_price,
                        from_currency=StromligningConstants.DEFAULT_CURRENCY,
                        from_unit=EnergyUnit.KWH  # Already in kWh
                    )
                    
                    # Store in hourly prices
                    hour_str = f"{local_dt.hour:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)
                    
                    # Check if this is current hour
                    if local_dt.hour == current_hour and local_dt.date() == now.date():
                        current_price = converted_price
                        raw_values["current_price"] = {
                            "raw": total_price,
                            "unit": f"{StromligningConstants.DEFAULT_CURRENCY}/kWh",
                            "components": {
                                StromligningConstants.PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                                StromligningConstants.PRICE_COMPONENTS["GRID"]: grid_price,
                                StromligningConstants.PRICE_COMPONENTS["TAX"]: tax_price
                            },
                            "final": converted_price,
                            "currency": self._currency,
                            "vat_rate": self.vat  # Note: VAT is already included in Stromligning data
                        }
                    
                    # Check if this is next hour
                    next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                    if local_dt.hour == next_hour.hour and local_dt.date() == next_hour.date():
                        next_hour_price = converted_price
                        raw_values["next_hour_price"] = {
                            "raw": total_price,
                            "unit": f"{StromligningConstants.DEFAULT_CURRENCY}/kWh",
                            "components": {
                                StromligningConstants.PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                                StromligningConstants.PRICE_COMPONENTS["GRID"]: grid_price,
                                StromligningConstants.PRICE_COMPONENTS["TAX"]: tax_price
                            },
                            "final": converted_price,
                            "currency": self._currency,
                            "vat_rate": self.vat
                        }
                
                except Exception as e:
                    _LOGGER.warning(f"Error processing price entry: {e}")
                    continue
            
            if not all_prices:
                _LOGGER.error("No valid prices extracted from Stromligning data")
                return None
            
            # Calculate day average
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
            
            # Find peak and off-peak prices
            peak_price = max(all_prices) if all_prices else None
            off_peak_price = min(all_prices) if all_prices else None
            
            # Store value calculations in raw_values
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
            
            # Build final result
            result = {
                "current_price": current_price if 'current_price' in locals() else None,
                "next_hour_price": next_hour_price if 'next_hour_price' in locals() else None,
                "day_average_price": day_average_price,
                "peak_price": peak_price,
                "off_peak_price": off_peak_price,
                "hourly_prices": hourly_prices,
                "raw_prices": raw_prices,
                "raw_values": raw_values,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data_source": "Stromligning.dk",
                "currency": self._currency,
                "price_area": price_area
            }
            
            return result
            
        except Exception as e:
            _LOGGER.error(f"Error processing Stromligning data: {e}", exc_info=True)
            return None

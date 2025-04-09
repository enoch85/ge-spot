"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
import datetime
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.converters import localize_datetime
from ..const import (Config, DisplayUnit, Currency, EnergyUnit)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY"

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using AEMO API."""
    client = ApiClient(session=session)
    try:
        # Settings
        use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS
        vat = config.get(Config.VAT, 0)
        
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None
        
        # Process data
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session)
        
        # Add metadata
        if result:
            result["data_source"] = "AEMO"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from AEMO."""
    try:
        if reference_time is None:
            reference_time = datetime.datetime.now(datetime.timezone.utc)
            
        # Format the time for AEMO API
        formatted_time = reference_time.strftime("%Y%m%dT%H%M%S")
        
        params = {
            "time": formatted_time,
        }

        _LOGGER.debug(f"Fetching AEMO with params: {params}")

        return await client.fetch(BASE_URL, params=params)
    except Exception as e:
        _LOGGER.error(f"Error fetching AEMO data: {e}")
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from AEMO."""
    if not data:
        _LOGGER.error("No data received from AEMO API")
        return None

    try:
        # Get current time
        now = reference_time or datetime.datetime.now(datetime.timezone.utc)
        if hass:
            now = localize_datetime(now, hass)
        current_hour = now.hour

        # Note: This is a placeholder implementation until actual AEMO API format is known
        _LOGGER.warning("AEMO API processing is not fully implemented - API format TBD")

        # Target currency is AUD for Australia
        api_currency = "AUD"

        # Initialize result structure with minimal data to avoid errors elsewhere
        result = {
            "current_price": None,
            "next_hour_price": None,
            "day_average_price": None,
            "peak_price": None,
            "off_peak_price": None,
            "hourly_prices": {},
            "raw_values": {},
            "raw_prices": []
        }

        # Parse data and extract hourly prices
        # Placeholder implementation - would need adjusting based on actual API response
        if isinstance(data, dict) and "data" in data:
            # Example parsing based on assumed format - would need adjustment
            regions_data = data.get("data", {}).get("regionPrices", [])
            
            hourly_prices = {}
            all_prices = []
            
            # Find data for requested area
            region_data = None
            for region in regions_data:
                if region.get("regionId", "") == area:
                    region_data = region
                    break
            
            if region_data:
                # Extract prices
                price_data = region_data.get("prices", [])
                
                for entry in price_data:
                    # Example extraction - adjust based on actual format
                    timestamp = entry.get("timestamp")
                    price = entry.get("price")
                    
                    if not timestamp or price is None:
                        continue
                    
                    # Parse timestamp
                    dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if hass:
                        dt = localize_datetime(dt, hass)
                    
                    # Store raw price
                    result["raw_prices"].append({
                        "start": dt.isoformat(),
                        "end": (dt + datetime.timedelta(hours=1)).isoformat(),
                        "price": price
                    })
                    
                    # Convert price
                    converted_price = await async_convert_energy_price(
                        price=price,
                        from_unit=EnergyUnit.MWH,
                        to_unit="kWh",
                        from_currency=api_currency,
                        to_currency=currency,
                        vat=vat,
                        to_subunit=use_subunit,
                        session=session
                    )
                    
                    # Store hourly price
                    hour_str = f"{dt.hour:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)
                    
                    # Check if current hour
                    if dt.hour == current_hour and dt.date() == now.date():
                        result["current_price"] = converted_price
                        result["raw_values"]["current_price"] = {
                            "raw": price,
                            "unit": f"{api_currency}/MWh",
                            "final": converted_price,
                            "currency": currency,
                            "vat_rate": vat
                        }
                    
                    # Check if next hour
                    next_hour = (current_hour + 1) % 24
                    if dt.hour == next_hour and dt.date() == now.date():
                        result["next_hour_price"] = converted_price
                        result["raw_values"]["next_hour_price"] = {
                            "raw": price,
                            "unit": f"{api_currency}/MWh",
                            "final": converted_price,
                            "currency": currency,
                            "vat_rate": vat
                        }
                
                # Check if we have exactly 24 hourly prices
                if len(hourly_prices) != 24 and len(hourly_prices) > 0:
                    _LOGGER.warning(f"Expected 24 hourly prices, got {len(hourly_prices)}. Prices may be incomplete.")
                
                # Add hourly prices
                result["hourly_prices"] = hourly_prices
                
                # Calculate statistics
                if all_prices:
                    result["day_average_price"] = sum(all_prices) / len(all_prices)
                    result["peak_price"] = max(all_prices)
                    result["off_peak_price"] = min(all_prices)
                    
                    # Store raw values for statistics
                    result["raw_values"]["day_average_price"] = {
                        "value": result["day_average_price"],
                        "calculation": "average of all hourly prices"
                    }
                    result["raw_values"]["peak_price"] = {
                        "value": result["peak_price"],
                        "calculation": "maximum of all hourly prices"
                    }
                    result["raw_values"]["off_peak_price"] = {
                        "value": result["off_peak_price"],
                        "calculation": "minimum of all hourly prices"
                    }

        return result

    except Exception as e:
        _LOGGER.error(f"Error processing AEMO data: {e}")
        return None

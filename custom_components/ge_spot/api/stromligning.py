"""API handler for Stromligning.dk."""
import logging
import datetime
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.converters import localize_datetime, ensure_timezone_aware
from ..timezone.parsers import parse_datetime
from ..const import (Config, DisplayUnit, Currency, EnergyUnit)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://stromligning.dk/api/prices"
DEFAULT_AREA = "DK1"
DEFAULT_CURRENCY = "DKK"
PRICE_COMPONENTS = {
    "ELECTRICITY": "electricity",
    "GRID": "grid",
    "TAX": "tax"
}

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Stromligning.dk API."""
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
            result["data_source"] = "Stromligning.dk"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Stromligning.dk API."""
    try:
        if reference_time is None:
            reference_time = datetime.datetime.now(datetime.timezone.utc)
            
        today = reference_time.date()
        tomorrow = today + datetime.timedelta(days=1)
        yesterday = today - datetime.timedelta(days=1)
        
        # Format dates for API query
        from_date = yesterday.isoformat() + "T00:00:00"
        to_date = tomorrow.isoformat() + "T23:59:59"
        
        # Get area code - use the configured area (typically DK1 or DK2)
        area_code = config.get("area", DEFAULT_AREA)
        
        params = {
            "from": from_date,
            "to": to_date,
            "priceArea": area_code,
            "lean": "false"  # We want the detailed response
        }
        
        _LOGGER.debug(f"Fetching Stromligning with params: {params}")
        
        return await client.fetch(BASE_URL, params=params)
    except Exception as e:
        _LOGGER.error(f"Error fetching Stromligning data: {e}")
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from Stromligning.dk."""
    if not data or "prices" not in data or not data["prices"]:
        _LOGGER.error("No valid data received from Stromligning API")
        return None
    
    try:
        # Extract price area
        price_area = data.get("priceArea", area)
        
        # Get current time
        now = reference_time or datetime.datetime.now(datetime.timezone.utc)
        if hass:
            now = localize_datetime(now, hass)
        current_hour = now.hour
        
        # Initialize result structure
        result = {
            "current_price": None,
            "next_hour_price": None,
            "day_average_price": None,
            "peak_price": None,
            "off_peak_price": None,
            "hourly_prices": {},
            "raw_values": {},
            "raw_prices": [],
            "price_area": price_area
        }
        
        # Process prices
        all_prices = []
        hourly_prices = {}
        
        for price_entry in data["prices"]:
            # Extract timestamp and price
            if "date" not in price_entry or "price" not in price_entry:
                continue
            
            try:
                # Parse timestamp
                timestamp_str = price_entry["date"]
                timestamp = parse_datetime(timestamp_str)
                
                # Convert to local time
                local_dt = timestamp
                if hass:
                    local_dt = localize_datetime(timestamp, hass)
                
                # For Danish areas, use only the electricity component (not grid fees or taxes)
                # This matches the Nord Pool spot price
                if area.startswith("DK"):
                    # Extract only electricity price for Danish areas
                    total_price = price_entry["details"]["electricity"]["total"]
                else:
                    # Use total price for non-Danish areas
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
                result["raw_prices"].append({
                    "start": local_dt.isoformat(),
                    "end": (local_dt + datetime.timedelta(hours=1)).isoformat(),
                    "price": total_price,
                    "components": {
                        PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                        PRICE_COMPONENTS["GRID"]: grid_price,
                        PRICE_COMPONENTS["TAX"]: tax_price
                    }
                })
                
                # Convert price. Note: Stromligning returns prices in DKK/kWh already
                converted_price = await async_convert_energy_price(
                    price=total_price,
                    from_unit=EnergyUnit.KWH,
                    to_unit="kWh",
                    from_currency=DEFAULT_CURRENCY,
                    to_currency=currency,
                    vat=vat,  # Note: VAT is already included in Stromligning data
                    to_subunit=use_subunit,
                    session=session
                )
                
                # Store hourly price
                hour_str = f"{local_dt.hour:02d}:00"
                hourly_prices[hour_str] = converted_price
                all_prices.append(converted_price)
                
                # Check if current hour
                if local_dt.hour == current_hour and local_dt.date() == now.date():
                    result["current_price"] = converted_price
                    result["raw_values"]["current_price"] = {
                        "raw": total_price,
                        "unit": f"{DEFAULT_CURRENCY}/kWh",
                        "components": {
                            PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                            PRICE_COMPONENTS["GRID"]: grid_price,
                            PRICE_COMPONENTS["TAX"]: tax_price
                        },
                        "final": converted_price,
                        "currency": currency,
                        "vat_rate": vat
                    }
                
                # Check if next hour
                next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                if local_dt.hour == next_hour.hour and local_dt.date() == next_hour.date():
                    result["next_hour_price"] = converted_price
                    result["raw_values"]["next_hour_price"] = {
                        "raw": total_price,
                        "unit": f"{DEFAULT_CURRENCY}/kWh",
                        "components": {
                            PRICE_COMPONENTS["ELECTRICITY"]: electricity_price,
                            PRICE_COMPONENTS["GRID"]: grid_price,
                            PRICE_COMPONENTS["TAX"]: tax_price
                        },
                        "final": converted_price,
                        "currency": currency,
                        "vat_rate": vat
                    }
            
            except Exception as e:
                _LOGGER.warning(f"Error processing price entry: {e}")
                continue
        
        if not all_prices:
            _LOGGER.error("No valid prices extracted from Stromligning data")
            return None
        
        # Check if we have exactly 24 hourly prices for today
        today_prices = [p for p in result["raw_prices"] 
                        if parse_datetime(p["start"]).date() == now.date()]
        if len(today_prices) != 24 and len(today_prices) > 0:
            _LOGGER.warning(f"Expected 24 hourly prices for today, got {len(today_prices)}. Prices may be incomplete.")
        
        # Add hourly prices
        result["hourly_prices"] = hourly_prices
        
        # Calculate statistics
        result["day_average_price"] = sum(all_prices) / len(all_prices)
        result["peak_price"] = max(all_prices)
        result["off_peak_price"] = min(all_prices)
        
        # Store value calculations in raw_values
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
        _LOGGER.error(f"Error processing Stromligning data: {e}")
        return None

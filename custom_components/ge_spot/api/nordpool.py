"""API handler for Nordpool."""
import logging
import datetime
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.parsers import parse_datetime
from ..timezone.converters import localize_datetime
from ..const import (
    Currency, AreaMapping, TimeFormat, EnergyUnit, 
    Network, Config, DisplayUnit
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.NORDPOOL

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Nordpool API."""
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
            result["data_source"] = "Nordpool"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Nordpool."""
    try:
        if reference_time is None:
            reference_time = datetime.datetime.now(datetime.timezone.utc)
        
        today = reference_time.strftime(TimeFormat.DATE_ONLY)
        tomorrow = (reference_time + datetime.timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)
        
        # Map area to Nordpool delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)
        _LOGGER.debug(f"Fetching Nordpool data for area: {delivery_area}")
        
        # Fetch today's data
        params = {
            "currency": Currency.EUR,  # Always request in EUR, convert later
            "date": today,
            "market": "Elspot",
            "deliveryArea": delivery_area
        }
        
        today_data = await client.fetch(BASE_URL, params=params)
        
        # Fetch tomorrow's data if after 13:00 CET
        tomorrow_data = None
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_cet = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
        
        if now_cet.hour >= 13:
            params["date"] = tomorrow
            tomorrow_data = await client.fetch(BASE_URL, params=params)
        
        return {
            "today": today_data,
            "tomorrow": tomorrow_data,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    except Exception as e:
        _LOGGER.error(f"Error fetching Nordpool data: {e}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from Nordpool."""
    if not data or "today" not in data:
        return None
    
    today_data = data["today"]
    tomorrow_data = data.get("tomorrow")
    
    if "multiAreaEntries" not in today_data:
        _LOGGER.error("Missing multiAreaEntries in Nordpool data")
        return None
    
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
        "raw_prices": []
    }
    
    # Process today's data
    all_prices = []
    hourly_prices = {}
    
    for entry in today_data.get("multiAreaEntries", []):
        if not isinstance(entry, dict) or "entryPerArea" not in entry:
            continue
        
        if area not in entry["entryPerArea"]:
            continue
        
        # Extract values
        start_time = entry.get("deliveryStart")
        end_time = entry.get("deliveryEnd")
        raw_price = entry["entryPerArea"][area]
        
        # Store in raw data
        result["raw_prices"].append({
            "start": start_time,
            "end": end_time,
            "price": raw_price
        })
        
        # Convert to float if needed
        if isinstance(raw_price, str):
            try:
                raw_price = float(raw_price)
            except (ValueError, TypeError):
                continue
        
        try:
            # Parse timestamp
            dt = parse_datetime(start_time)
            
            # Convert to local time
            local_dt = dt
            if hass:
                local_dt = localize_datetime(dt, hass)
            
            # Convert price
            converted_price = await async_convert_energy_price(
                price=raw_price,
                from_unit=EnergyUnit.MWH,
                to_unit="kWh",
                from_currency=Currency.EUR,
                to_currency=currency,
                vat=vat,
                to_subunit=use_subunit,
                session=session
            )
            
            # Store hourly price
            hour = local_dt.hour
            hour_str = f"{hour:02d}:00"
            hourly_prices[hour_str] = converted_price
            all_prices.append(converted_price)
            
            # Check if current hour
            if hour == current_hour:
                result["current_price"] = converted_price
                result["raw_values"]["current_price"] = {
                    "raw": raw_price,
                    "unit": f"{Currency.EUR}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }
            
            # Check if next hour
            if hour == (current_hour + 1) % 24:
                result["next_hour_price"] = converted_price
                result["raw_values"]["next_hour_price"] = {
                    "raw": raw_price,
                    "unit": f"{Currency.EUR}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }
                
        except Exception as e:
            _LOGGER.error(f"Error processing timestamp {start_time}: {e}")
            continue
    
    # Check if we have exactly 24 prices
    if len(hourly_prices) != 24 and len(hourly_prices) > 0:
        _LOGGER.warning(f"Expected 24 hourly prices, got {len(hourly_prices)}. Prices may be incomplete.")
    
    # Add hourly prices
    result["hourly_prices"] = hourly_prices
    
    # Calculate statistics
    if all_prices:
        result["day_average_price"] = sum(all_prices) / len(all_prices)
        result["peak_price"] = max(all_prices)
        result["off_peak_price"] = min(all_prices)
        
        # Add raw values for stats
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
    
    # Process tomorrow data if available
    if tomorrow_data and "multiAreaEntries" in tomorrow_data:
        tomorrow_hourly_prices = {}
        tomorrow_prices = []
        tomorrow_raw_prices = []
        
        # Process similar to today's data
        for entry in tomorrow_data.get("multiAreaEntries", []):
            if not isinstance(entry, dict) or "entryPerArea" not in entry:
                continue
            
            if area not in entry["entryPerArea"]:
                continue
            
            # Extract values
            start_time = entry.get("deliveryStart")
            end_time = entry.get("deliveryEnd")
            raw_price = entry["entryPerArea"][area]
            
            # Store in raw data
            tomorrow_raw_prices.append({
                "start": start_time,
                "end": end_time,
                "price": raw_price
            })
            
            # Convert to float if needed
            if isinstance(raw_price, str):
                try:
                    raw_price = float(raw_price)
                except (ValueError, TypeError):
                    continue
            
            # Similar processing as for today's data
            try:
                dt = parse_datetime(start_time)
                local_dt = dt
                if hass:
                    local_dt = localize_datetime(dt, hass)
                
                converted_price = await async_convert_energy_price(
                    price=raw_price,
                    from_unit=EnergyUnit.MWH,
                    to_unit="kWh",
                    from_currency=Currency.EUR,
                    to_currency=currency,
                    vat=vat,
                    to_subunit=use_subunit,
                    session=session
                )
                
                hour_str = f"{local_dt.hour:02d}:00"
                tomorrow_hourly_prices[hour_str] = converted_price
                tomorrow_prices.append(converted_price)
                
            except Exception as e:
                _LOGGER.error(f"Error processing tomorrow timestamp {start_time}: {e}")
                continue
        
        # Check for exactly 24 prices for tomorrow
        if len(tomorrow_hourly_prices) != 24 and len(tomorrow_hourly_prices) > 0:
            _LOGGER.warning(f"Expected 24 prices for tomorrow, got {len(tomorrow_hourly_prices)}.")
                
        # Add tomorrow data
        if tomorrow_prices:
            result["tomorrow_hourly_prices"] = tomorrow_hourly_prices
            result["raw_tomorrow"] = tomorrow_raw_prices
            result["tomorrow_average_price"] = sum(tomorrow_prices) / len(tomorrow_prices)
            result["tomorrow_peak_price"] = max(tomorrow_prices)
            result["tomorrow_off_peak_price"] = min(tomorrow_prices)
            result["tomorrow_valid"] = len(tomorrow_prices) >= 20
    
    return result

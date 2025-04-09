"""API handler for Energi Data Service."""
import logging
import datetime
import json
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.parsers import parse_datetime
from ..timezone.converters import localize_datetime
from ..const import (Config, DisplayUnit, EnergyUnit)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Energi Data Service API."""
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
            result["data_source"] = "EnergiDataService"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Energi Data Service."""
    if reference_time is None:
        reference_time = datetime.datetime.now(datetime.timezone.utc)
    
    today = reference_time.strftime("%Y-%m-%d")
    tomorrow = (reference_time + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # Use area from config
    area_code = config.get("area", "DK1")  # Default to Western Denmark

    params = {
        "start": f"{today}T00:00",
        "end": f"{tomorrow}T00:00",
        "filter": json.dumps({"PriceArea": area_code}),
        "sort": "HourDK",
        "timezone": "dk",
    }

    _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

    return await client.fetch(BASE_URL, params=params)

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from Energi Data Service."""
    if not data or "records" not in data or not data["records"]:
        return None

    records = data["records"]
    
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

    # Get the API's currency (default to DKK for Energi Data Service)
    api_currency = data.get("currency", "DKK")
    
    # Process each record
    all_prices = []
    hourly_prices = {}
    
    for record in records:
        try:
            # Parse timestamp
            hour_dk = parse_datetime(record["HourDK"])
            if hass:
                hour_dk = localize_datetime(hour_dk, hass)
            
            # Store raw price from API
            raw_price = record.get("SpotPriceDKK", 0)
            if not isinstance(raw_price, (int, float)):
                try:
                    raw_price = float(raw_price)
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Invalid price value: {raw_price}")
                    continue
            
            # Store in raw prices list
            result["raw_prices"].append({
                "start": hour_dk.isoformat(),
                "end": (hour_dk + datetime.timedelta(hours=1)).isoformat(),
                "price": raw_price
            })
            
            # Convert price
            converted_price = await async_convert_energy_price(
                price=raw_price,
                from_unit=EnergyUnit.MWH,
                to_unit="kWh",
                from_currency=api_currency,
                to_currency=currency,
                vat=vat,
                to_subunit=use_subunit,
                session=session
            )
            
            # Store hourly price
            hour_str = f"{hour_dk.hour:02d}:00"
            hourly_prices[hour_str] = converted_price
            all_prices.append(converted_price)
            
            # Check if current hour
            if hour_dk.hour == current_hour and hour_dk.day == now.day:
                result["current_price"] = converted_price
                result["raw_values"]["current_price"] = {
                    "raw": raw_price,
                    "unit": f"{api_currency}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }
            
            # Check if next hour
            next_hour = (current_hour + 1) % 24
            if hour_dk.hour == next_hour and hour_dk.day == now.day:
                result["next_hour_price"] = converted_price
                result["raw_values"]["next_hour_price"] = {
                    "raw": raw_price,
                    "unit": f"{api_currency}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }
        except Exception as e:
            _LOGGER.error(f"Error processing record: {e}")
            continue
    
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
    
    return result

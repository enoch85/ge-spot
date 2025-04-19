"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.network import Network
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import Nordpool
from .parsers.nordpool_parser import NordpoolPriceParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.NORDPOOL

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
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
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session, config)

        # Add metadata
        if result:
            result["data_source"] = "Nordpool"
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency

        return result
    finally:
        await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Nordpool using a single API call with expanded date range."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try - similar to ENTSO-E approach
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)
        
        # Try different date ranges to maximize chance of getting both today and tomorrow data
        for start_date, end_date in date_ranges:
            # Use the date range parameters
            start_date_str = start_date.strftime(TimeFormat.DATE_ONLY)
            end_date_str = end_date.strftime(TimeFormat.DATE_ONLY)
            
            # If start and end date are the same, use a single date parameter
            if start_date_str == end_date_str:
                params = {
                    "currency": Currency.EUR,
                    "date": start_date_str,
                    "market": "DayAhead",
                    "deliveryArea": delivery_area
                }
            else:
                # Use a date range - Nordpool API doesn't support true date ranges,
                # so we request the end date which should include data for that day
                params = {
                    "currency": Currency.EUR,
                    "date": end_date_str,
                    "market": "DayAhead",
                    "deliveryArea": delivery_area
                }
            
            _LOGGER.debug(f"Trying Nordpool with date range: {start_date_str} to {end_date_str}, using date param: {params['date']}")
            response = await client.fetch(BASE_URL, params=params)
            
            if response and isinstance(response, dict) and "multiAreaEntries" in response:
                # Check if we got data
                entries = response.get("multiAreaEntries", [])
                if entries and any(area in entry.get("entryPerArea", {}) for entry in entries):
                    _LOGGER.info(f"Successfully fetched Nordpool data for area {area} ({len(entries)} entries)")
                    
                    # Log some details about the data timestamps to help debug
                    for entry in entries[:3]:  # Log a few entries for debugging
                        if "deliveryStart" in entry:
                            _LOGGER.debug(f"Sample entry deliveryStart: {entry['deliveryStart']}")
                    
                    # Return the data directly, similar to ENTSO-E structure
                    return response
            
            _LOGGER.debug(f"No data found for date range {start_date_str} to {end_date_str}, trying next range")
        
        # If we've tried all date ranges and still don't have data
        _LOGGER.warning(f"No data found for Nordpool area {area} after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Nordpool."""
    if not data or "multiAreaEntries" not in data:
        _LOGGER.error("Missing or invalid multiAreaEntries in Nordpool data")
        return None

    # Initialize timezone service with area and config to use area-specific timezone
    tz_service = TimezoneService(hass, area, config)
    _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

    # Extract source timezone from data or use default for Nordpool
    source_timezone = tz_service.extract_source_timezone(data, Source.NORDPOOL)
    _LOGGER.debug(f"Using source timezone for Nordpool: {source_timezone}")

    # Initialize result structure similar to ENTSO-E
    result = {
        "current_price": None,
        "next_hour_price": None,
        "day_average_price": None,
        "peak_price": None,
        "off_peak_price": None,
        "hourly_prices": {},
        "raw_values": {},
        "raw_prices": [],
        "api_timezone": source_timezone  # Store API timezone for reference
    }

    # Store raw price data for reference
    for entry in data.get("multiAreaEntries", []):
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

    try:
        # Use the NordpoolPriceParser to parse hourly prices
        parser = NordpoolPriceParser()

        # Parse hourly prices with ISO timestamps
        raw_hourly_prices = parser.parse_hourly_prices({"data": data}, area)
        
        # Log the raw hourly prices with ISO timestamps to help with debugging
        if raw_hourly_prices:
            _LOGGER.debug(f"Raw hourly prices with ISO timestamps: {list(raw_hourly_prices.items())[:5]} ({len(raw_hourly_prices)} total)")
            
            # Convert hourly prices to area-specific timezone (or HA timezone) in a single step
            converted_hourly_prices = tz_service.normalize_hourly_prices(
                raw_hourly_prices, source_timezone)

            # Apply price conversions (currency, VAT, etc.)
            for hour_str, price in converted_hourly_prices.items():
                converted_price = await async_convert_energy_price(
                    price=price,
                    from_unit=EnergyUnit.MWH,
                    to_unit="kWh",
                    from_currency=Currency.EUR,
                    to_currency=currency,
                    vat=vat,
                    to_subunit=use_subunit,
                    session=session
                )

                result["hourly_prices"][hour_str] = converted_price

            # Get current and next hour prices
            current_hour_key = tz_service.get_current_hour_key()
            if current_hour_key in result["hourly_prices"]:
                result["current_price"] = result["hourly_prices"][current_hour_key]
                result["raw_values"]["current_price"] = {
                    "raw": raw_hourly_prices.get(current_hour_key),
                    "unit": f"{Currency.EUR}/MWh",
                    "final": result["current_price"],
                    "currency": currency,
                    "vat_rate": vat
                }

            # Calculate next hour
            current_hour = int(current_hour_key.split(":")[0])
            next_hour = (current_hour + 1) % 24
            next_hour_key = f"{next_hour:02d}:00"

            if next_hour_key in result["hourly_prices"]:
                result["next_hour_price"] = result["hourly_prices"][next_hour_key]
                result["raw_values"]["next_hour_price"] = {
                    "raw": raw_hourly_prices.get(next_hour_key),
                    "unit": f"{Currency.EUR}/MWh",
                    "final": result["next_hour_price"],
                    "currency": currency,
                    "vat_rate": vat
                }

            # Calculate statistics
            prices = list(result["hourly_prices"].values())
            if prices:
                result["day_average_price"] = sum(prices) / len(prices)
                result["peak_price"] = max(prices)
                result["off_peak_price"] = min(prices)

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
    except Exception as e:
        _LOGGER.error(f"Error processing Nordpool data: {e}", exc_info=True)
        return None

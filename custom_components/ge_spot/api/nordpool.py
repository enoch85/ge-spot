"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta, time
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
    """Fetch data from Nordpool using date ranges similar to ENTSO-E approach."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try - just like ENTSO-E
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Try both today and tomorrow in the same request if possible, or use separate requests
        # First, attempt with tomorrow's date to maximize chances of getting tomorrow data
        for start_date, end_date in date_ranges:
            # Use the date range parameters
            start_date_str = start_date.strftime(TimeFormat.DATE_ONLY)
            end_date_str = end_date.strftime(TimeFormat.DATE_ONLY)

            params = {
                "currency": Currency.EUR,
                "date": end_date_str,  # Always use end date which is more likely to have data
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }

            _LOGGER.debug(f"Trying Nordpool fallback with date: {params['date']}")
            response = await client.fetch(BASE_URL, params=params)

            if response and isinstance(response, dict) and "multiAreaEntries" in response:
                # Check if we got data
                entries = response.get("multiAreaEntries", [])
                if entries and any(area in entry.get("entryPerArea", {}) for entry in entries):
                    _LOGGER.info(f"Successfully fetched Nordpool data via fallback for area {area} ({len(entries)} entries)")
                    return response

        # If we've tried all date ranges and still don't have data
        _LOGGER.warning(f"No data found for Nordpool area {area} after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Nordpool."""
    # Handle new combined format
    if isinstance(data, dict) and ("today" in data or "tomorrow" in data):
        _LOGGER.debug("Processing combined format data with today/tomorrow keys")
        # The data structure we need exists in one of these keys
        if "data" in data:
            # This is our fallback data (most likely tomorrow data)
            data_to_process = data["data"]
        elif "today" in data and data["today"]:
            # Use today data as the primary processing target
            data_to_process = data["today"]
        elif "tomorrow" in data and data["tomorrow"]:
            # Use tomorrow data if that's all we have
            data_to_process = data["tomorrow"]
        else:
            _LOGGER.error("No valid data found in combined format")
            return None

        if not data_to_process or "multiAreaEntries" not in data_to_process:
            _LOGGER.error("Missing or invalid multiAreaEntries in structured Nordpool data")
            return None

        # Update data reference to the part we're going to process
        data = data_to_process
    elif not data or "multiAreaEntries" not in data:
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
        "today_hourly_prices": {},
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

        # Parse hourly prices with ISO timestamps - use a consistent approach
        parser_result = parser.parse_hourly_prices({"data": data}, area)

        # Check if the parser returned a dict with both today_hourly_prices and tomorrow_hourly_prices
        raw_today_hourly_prices = {}
        raw_tomorrow_hourly_prices = {}

        if isinstance(parser_result, dict) and "today_hourly_prices" in parser_result and "tomorrow_hourly_prices" in parser_result:
            # New format with separated hourly prices
            raw_today_hourly_prices = parser_result["today_hourly_prices"]
            raw_tomorrow_hourly_prices = parser_result["tomorrow_hourly_prices"]
            _LOGGER.info(f"Using separated today ({len(raw_today_hourly_prices)}) and tomorrow ({len(raw_tomorrow_hourly_prices)}) data")
        else:
            # Old format with just hourly prices (or already migrated to today_hourly_prices)
            raw_today_hourly_prices = parser_result
            _LOGGER.debug(f"Using legacy format hourly prices format")

        # Log the raw hourly prices with ISO timestamps to help with debugging
        if raw_today_hourly_prices:
            _LOGGER.debug(f"Raw today hourly prices with ISO timestamps: {list(raw_today_hourly_prices.items())[:5]} ({len(raw_today_hourly_prices)} total)")

            # Convert and reorganize today and tomorrow prices based on local timezone
            converted_today, converted_tomorrow = tz_service.normalize_hourly_prices_with_tomorrow(
                raw_today_hourly_prices, raw_tomorrow_hourly_prices, source_timezone)

            # Initialize tomorrow_hourly_prices in result if not there
            if "tomorrow_hourly_prices" not in result:
                result["tomorrow_hourly_prices"] = {}

            # Apply price conversions for today prices
            for hour_str, price in converted_today.items():
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
                result["today_hourly_prices"][hour_str] = converted_price

            # Apply price conversions for tomorrow prices
            for hour_str, price in converted_tomorrow.items():
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
                result["tomorrow_hourly_prices"][hour_str] = converted_price

        # Get current and next hour prices
        current_hour_key = tz_service.get_current_hour_key()
        if current_hour_key in result["today_hourly_prices"]:
            result["current_price"] = result["today_hourly_prices"][current_hour_key]

            # Create raw value entry - match ENTSO-E approach for handling timestamps
            original_hour = int(current_hour_key.split(":")[0])
            current_dt = datetime.now().replace(hour=original_hour)
            current_dt = tz_service.converter.convert(current_dt, source_tz=source_timezone)
            original_hour_key = f"{current_dt.hour:02d}:00"

            result["raw_values"]["current_price"] = {
                "raw": raw_today_hourly_prices.get(original_hour_key),
                "unit": f"{Currency.EUR}/MWh",
                "final": result["current_price"],
                "currency": currency,
                "vat_rate": vat
            }

        # Calculate next hour
        current_hour = int(current_hour_key.split(":")[0])
        next_hour = (current_hour + 1) % 24
        next_hour_key = f"{next_hour:02d}:00"

        if next_hour_key in result["today_hourly_prices"]:
            result["next_hour_price"] = result["today_hourly_prices"][next_hour_key]
            result["raw_values"]["next_hour_price"] = {
                "raw": raw_today_hourly_prices.get(next_hour_key),
                "unit": f"{Currency.EUR}/MWh",
                "final": result["next_hour_price"],
                "currency": currency,
                "vat_rate": vat
            }

        # Calculate statistics
        prices = list(result["today_hourly_prices"].values())
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

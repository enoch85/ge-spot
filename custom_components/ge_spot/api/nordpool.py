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
    """Fetch data from Nordpool."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try
        # For Nordpool, we need to handle today and tomorrow separately
        # We'll use the date range utility to generate the ranges, but we'll process them differently
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Fetch today's data (first range is today to tomorrow)
        today_start, today_end = date_ranges[0]
        today = today_start.strftime(TimeFormat.DATE_ONLY)

        params_today = {
            "currency": Currency.EUR,
            "date": today,
            "market": "DayAhead",
            "deliveryArea": delivery_area
        }

        today_data = await client.fetch(BASE_URL, params=params_today)

        # Try to fetch tomorrow's data if it's after 13:00 CET (when typically available)
        tomorrow_data = None
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))

        if now_cet.hour >= 13:
            # Use the third range which is today to day after tomorrow
            # Extract tomorrow's date from it
            if len(date_ranges) >= 3:
                _, tomorrow_end = date_ranges[2]
                tomorrow = tomorrow_end.strftime(TimeFormat.DATE_ONLY)
            else:
                # Fallback to simple calculation if needed
                tomorrow = (reference_time + timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)

            params_tomorrow = {
                "currency": Currency.EUR,
                "date": tomorrow,
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }

            tomorrow_data = await client.fetch(BASE_URL, params=params_tomorrow)

        return {
            "today": today_data,
            "tomorrow": tomorrow_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Nordpool."""
    if not data or "today" not in data:
        return None

    today_data = data["today"]
    tomorrow_data = data.get("tomorrow")

    if not today_data or "multiAreaEntries" not in today_data:
        _LOGGER.error("Missing or invalid multiAreaEntries in Nordpool data")
        return None

    # Initialize timezone service with area and config to use area-specific timezone
    tz_service = TimezoneService(hass, area, config)
    _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

    # Extract source timezone from data or use default for Nordpool
    source_timezone = tz_service.extract_source_timezone(today_data, Source.NORDPOOL)
    _LOGGER.debug(f"Using source timezone for Nordpool: {source_timezone}")

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
        "api_timezone": source_timezone  # Store API timezone for reference
    }

    # Store raw price data for reference
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

    try:
        # Use the NordpoolPriceParser to parse hourly prices
        parser = NordpoolPriceParser()

        # Parse today's hourly prices
        raw_hourly_prices = parser.parse_hourly_prices(data, area)

        # Convert hourly prices to area-specific timezone (or HA timezone) in a single step
        if raw_hourly_prices:
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

        # Process tomorrow data if available
        if tomorrow_data and "multiAreaEntries" in tomorrow_data:
            # Parse tomorrow's hourly prices
            tomorrow_raw_prices = parser.parse_tomorrow_prices(data, area)

            # Get tomorrow's date in HA timezone for proper conversion
            tomorrow_date = tz_service.converter.convert(datetime.now(), source_tz=source_timezone).date() + timedelta(days=1)

            # Convert tomorrow hourly prices to area-specific timezone (or HA timezone) in a single step
            if tomorrow_raw_prices:
                tomorrow_converted_prices = tz_service.normalize_hourly_prices(
                    tomorrow_raw_prices, source_timezone, tomorrow_date)

                # Apply price conversions
                result["tomorrow_hourly_prices"] = {}
                for hour_str, price in tomorrow_converted_prices.items():
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

                # Calculate tomorrow statistics
                tomorrow_prices = list(result["tomorrow_hourly_prices"].values())
                if tomorrow_prices:
                    result["tomorrow_average_price"] = sum(tomorrow_prices) / len(tomorrow_prices)
                    result["tomorrow_peak_price"] = max(tomorrow_prices)
                    result["tomorrow_off_peak_price"] = min(tomorrow_prices)
                    result["tomorrow_valid"] = len(tomorrow_prices) >= 20
    except Exception as e:
        _LOGGER.error(f"Error processing Nordpool data: {e}", exc_info=True)
        return None

    return result

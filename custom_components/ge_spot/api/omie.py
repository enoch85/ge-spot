"""API handler for OMIE (Operador del Mercado Ibérico de Energía)."""
import logging
from datetime import datetime, timezone, timedelta, time
import csv
import io
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.api import Omie
from .parsers.omie_parser import OmieParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

# Base URL template
BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using OMIE API.
    
    This function only fetches raw data from the API without any processing.
    Processing is handled by the data managers.
    """
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Return simplified format with just raw data and metadata
        # This follows the new simplified API response format
        result = {
            "raw_data": raw_data,
            "api_timezone": "Europe/Madrid",  # OMIE API uses CET/CEST timezone
            "currency": Currency.EUR  # OMIE API returns prices in EUR
        }

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from OMIE."""
    try:
        # Get proper date in the local timezone of the area (ES/PT)
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.OMIE)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # OMIE uses the start date for its files
            target_date = start_date.date()
            year = str(target_date.year)
            month = str.zfill(str(target_date.month), 2)
            day = str.zfill(str(target_date.day), 2)

            # Build OMIE URL using template
            url = BASE_URL_TEMPLATE.format(
                year=year, month=month, day=day
            )

            _LOGGER.debug(f"Fetching OMIE data from URL: {url}")

            # Fetch data with built-in retry mechanism - use ISO-8859-1 encoding for Spanish/Portuguese characters
            response = await client.fetch(url, timeout=30, encoding='iso-8859-1')

            # OMIE returns HTML for non-existent files rather than 404
            if not response:
                _LOGGER.warning(f"No response from OMIE for {day}_{month}_{year}, trying next date range")
                continue

            if isinstance(response, str) and ("<html" in response.lower() or "<!doctype" in response.lower()):
                _LOGGER.warning(f"HTML response from OMIE for {day}_{month}_{year}, likely data not available yet, trying next date range")
                continue

            # If we got a valid response, return it
            _LOGGER.info(f"Successfully fetched OMIE data for {day}_{month}_{year}")
            return {
                "raw_data": response,
                "date_str": f"{day}_{month}_{year}",
                "target_date": target_date,
                "url": url
            }

        # If we've tried all date ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from OMIE after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Failed to fetch data from OMIE: {e}")
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from OMIE."""
    if not data or "raw_data" not in data:
        return None

    try:
        # Get current time
        now = reference_time or datetime.now(timezone.utc)

        # Initialize timezone service with area and config to use area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Extract source timezone from OMIE data or use default
        source_timezone = tz_service.extract_source_timezone(data, Source.OMIE)

        if hass:
            now = tz_service.convert_to_ha_timezone(now)

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

        try:
            # Use the OmieParser to parse hourly prices
            parser = OmieParser()

            # Extract metadata
            metadata = parser.extract_metadata(data)
            api_currency = metadata.get("currency", Currency.EUR)

            # Add metadata to result
            if "date_str" in metadata:
                result["date_str"] = metadata["date_str"]

            if "target_date" in metadata:
                result["target_date"] = metadata["target_date"]

            if "url" in metadata:
                result["url"] = metadata["url"]

            # Parse hourly prices
            raw_hourly_prices = parser.parse_hourly_prices(data, area)

            # Create raw prices array for reference
            for hour_str, price in raw_hourly_prices.items():
                # Create a timezone-aware datetime
                hour = int(hour_str.split(":")[0])
                now_date = datetime.now().date()
                hour_time = datetime.combine(now_date, time(hour=hour))
                # Make it timezone-aware
                hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                end_time = hour_time + timedelta(hours=1)

                # Store raw price
                result["raw_prices"].append({
                    "start": hour_time.isoformat(),
                    "end": end_time.isoformat(),
                    "price": price
                })

            # Now convert hourly prices to area-specific timezone (or HA timezone) in a single step
            if raw_hourly_prices:
                converted_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_hourly_prices, source_timezone)

                # Apply price conversions (currency, VAT, etc.)
                for hour_str, price in converted_hourly_prices.items():
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
                    result["hourly_prices"][hour_str] = converted_price

                # Get current and next hour prices
                current_hour_key = tz_service.get_current_hour_key()
                if current_hour_key in result["hourly_prices"]:
                    result["current_price"] = result["hourly_prices"][current_hour_key]
                    result["raw_values"]["current_price"] = {
                        "raw": raw_hourly_prices.get(current_hour_key),
                        "unit": f"{api_currency}/MWh",
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
                        "unit": f"{api_currency}/MWh",
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

        except ValueError as e:
            _LOGGER.error(f"Error parsing OMIE data: {e}")
            return None

        return result

    except Exception as e:
        _LOGGER.error(f"Error processing OMIE data: {e}", exc_info=True)
        return None

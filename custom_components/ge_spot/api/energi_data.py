"""API handler for Energi Data Service."""
import logging
from datetime import datetime, timezone, timedelta, time
import json
from typing import Dict, Any, Optional

from ..timezone import TimezoneService
from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.energy import EnergyUnit
from .parsers.energi_data_parser import EnergiDataParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Energi Data Service API.
    
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
            "api_timezone": "Europe/Copenhagen",  # Energi Data Service API uses CET/CEST timezone
            "currency": "DKK"  # Energi Data Service API returns prices in DKK
        }

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Energi Data Service."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Generate date ranges to try
    date_ranges = generate_date_ranges(reference_time, Source.ENERGI_DATA_SERVICE)

    # Use area from config
    area_code = config.get("area", "DK1")  # Default to Western Denmark

    # Try each date range until we get a valid response
    for start_date, end_date in date_ranges:
        # Format dates for Energi Data Service API
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        params = {
            "start": f"{start_str}T00:00",
            "end": f"{end_str}T00:00",
            "filter": json.dumps({"PriceArea": area_code}),
            "sort": "HourDK",
            "timezone": "dk",
        }

        _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

        response = await client.fetch(BASE_URL, params=params)

        # Check if we got a valid response with records
        if response and isinstance(response, dict) and "records" in response and response["records"]:
            _LOGGER.info(f"Successfully fetched Energi Data Service data for {start_str} to {end_str}")
            return response
        else:
            _LOGGER.debug(f"No valid data from Energi Data Service for {start_str} to {end_str}, trying next range")

    # If we've tried all date ranges and still have no data, log a warning
    _LOGGER.warning("No valid data found from Energi Data Service after trying multiple date ranges")
    return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Energi Data Service."""
    if not data or "records" not in data or not data["records"]:
        return None

    # Get current time
    now = reference_time or datetime.now(timezone.utc)

    # Initialize timezone service with area and config to use area-specific timezone
    tz_service = TimezoneService(hass, area, config)
    _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

    # Extract source timezone from data or use default
    source_timezone = tz_service.extract_source_timezone(data, Source.ENERGI_DATA_SERVICE)

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
        # Use the EnergiDataParser to parse hourly prices
        parser = EnergiDataParser()

        # Extract metadata
        metadata = parser.extract_metadata(data)
        api_currency = metadata.get("currency", "DKK")

        # Add metadata to result
        if "area" in metadata:
            result["price_area"] = metadata["area"]

        if "dataset" in metadata:
            result["dataset"] = metadata["dataset"]

        if "has_eur_prices" in metadata:
            result["has_eur_prices"] = metadata["has_eur_prices"]

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

            # Create raw price entry
            raw_price_entry = {
                "start": hour_time.isoformat(),
                "end": end_time.isoformat(),
                "price_dkk": price
            }

            # Add EUR price if available
            if isinstance(result, dict) and result.get("has_eur_prices") and isinstance(data, dict) and "records" in data:
                # Find the record for this hour
                for record in data["records"]:
                    record_hour_dk = record.get("HourDK")
                    if record_hour_dk:
                        try:
                            record_dt = tz_service.parse_timestamp(record_hour_dk, source_timezone)
                            record_hour_str = f"{record_dt.hour:02d}:00"
                            if record_hour_str == hour_str and "SpotPriceEUR" in record:
                                raw_price_entry["price_eur"] = record["SpotPriceEUR"]
                                break
                        except Exception:
                            pass

            # Store raw price
            result["raw_prices"].append(raw_price_entry)

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
        _LOGGER.error(f"Error parsing Energi Data Service data: {e}")
        return None

    return result

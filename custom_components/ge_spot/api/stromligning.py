"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.api import Stromligning
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://stromligning.dk/api/prices"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
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
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session, config)

        # Add metadata
        if result:
            result["data_source"] = "Stromligning.dk"
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Stromligning.dk API."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.STROMLIGNING)

        # Get area code - use the configured area (typically DK1 or DK2)
        area_code = config.get("area", Stromligning.DEFAULT_AREA)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Stromligning API expects a wider range than just the start/end dates
            # We'll use the start date as "from" and add 2 days to the end date as "to"
            from_date = start_date.date().isoformat() + "T00:00:00"
            to_date = (end_date.date() + timedelta(days=1)).isoformat() + "T23:59:59"

            params = {
                "from": from_date,
                "to": to_date,
                "priceArea": area_code,
                "lean": "false"  # We want the detailed response
            }

            _LOGGER.debug(f"Fetching Stromligning with params: {params}")

            response = await client.fetch(BASE_URL, params=params)

            # Check if we got a valid response with prices
            if response and isinstance(response, dict) and "prices" in response and response["prices"]:
                _LOGGER.info(f"Successfully fetched Stromligning data for {from_date} to {to_date}")
                return response
            else:
                _LOGGER.debug(f"No valid data from Stromligning for {from_date} to {to_date}, trying next range")

        # If we've tried all date ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from Stromligning after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error fetching Stromligning data: {e}")
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Stromligning.dk."""
    if not data or "prices" not in data or not data["prices"]:
        _LOGGER.error("No valid data received from Stromligning API")
        return None

    try:
        # Get current time
        now = reference_time or datetime.now(timezone.utc)

        # Initialize timezone service with area and config to use area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Extract source timezone from data or use default
        source_timezone = tz_service.extract_source_timezone(data, Source.STROMLIGNING)

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
            "api_timezone": source_timezone,
            "price_components": {}  # Store detailed components
        }

        try:
            # Use the StromligningParser to parse hourly prices
            parser = StromligningParser()

            # Extract metadata
            metadata = parser.extract_metadata(data)
            api_currency = metadata.get("currency", Stromligning.DEFAULT_CURRENCY)

            # Add metadata to result
            if "price_area" in metadata:
                result["price_area"] = metadata["price_area"]
            elif isinstance(data, dict):
                result["price_area"] = data.get("priceArea", area)
            else:
                result["price_area"] = area

            if "has_components" in metadata:
                result["has_components"] = metadata["has_components"]

            if "component_types" in metadata:
                result["component_types"] = metadata["component_types"]

            # Parse hourly prices
            raw_hourly_prices = parser.parse_hourly_prices(data, area)

            # Get price components
            price_components = parser.get_price_components()
            if price_components:
                result["price_components"] = price_components

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
                    "price": price
                }

                # Add components if available
                if hour_str in price_components:
                    raw_price_entry["components"] = price_components[hour_str]

                # Store raw price
                result["raw_prices"].append(raw_price_entry)

            # Now convert hourly prices to area-specific timezone (or HA timezone) in a single step
            if raw_hourly_prices:
                converted_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_hourly_prices, source_timezone)

                # Apply price conversions (currency, VAT, etc.)
                for hour_str, price in converted_hourly_prices.items():
                    # Convert price. Note: Stromligning returns prices in DKK/kWh already
                    converted_price = await async_convert_energy_price(
                        price=price,
                        from_unit=EnergyUnit.KWH,
                        to_unit="kWh",
                        from_currency=api_currency,
                        to_currency=currency,
                        vat=vat,  # Note: VAT is already included in Stromligning data
                        to_subunit=use_subunit,
                        session=session
                    )

                    # Store hourly price
                    result["hourly_prices"][hour_str] = converted_price

                # Get current and next hour prices
                current_hour_key = tz_service.get_current_hour_key()
                if current_hour_key in result["hourly_prices"]:
                    result["current_price"] = result["hourly_prices"][current_hour_key]

                    # Get components for the current hour if available
                    current_hour_components = price_components.get(current_hour_key, {})

                    result["raw_values"]["current_price"] = {
                        "raw": raw_hourly_prices.get(current_hour_key),
                        "unit": f"{api_currency}/kWh",
                        "components": current_hour_components,
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

                    # Get components for the next hour if available
                    next_hour_components = price_components.get(next_hour_key, {})

                    result["raw_values"]["next_hour_price"] = {
                        "raw": raw_hourly_prices.get(next_hour_key),
                        "unit": f"{api_currency}/kWh",
                        "components": next_hour_components,
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
            _LOGGER.error(f"Error parsing Stromligning data: {e}")
            return None

        return result

    except Exception as e:
        _LOGGER.error(f"Error processing Stromligning data: {e}")
        return None

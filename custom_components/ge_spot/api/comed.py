"""API handler for ComEd Hourly Pricing."""
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, Optional, List
import asyncio
import json
import re

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.api import ComEd, SourceTimezone
from .parsers.comed_parser import ComedParser
from .base.data_fetch import create_skipped_response
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch electricity prices using ComEd Hourly Pricing API."""
    client = ApiClient(session=session)
    try:
        # Settings
        use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS
        vat = config.get(Config.VAT, 0)

        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            _LOGGER.warning(f"No data received from ComEd API for area {area}")
            return None

        # Process data
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session, config)

        # Add metadata
        if result:
            result["data_source"] = Source.DISPLAY_NAMES[Source.COMED]
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency
            result["area"] = area
            result["source_type"] = source_type

        return result
    except Exception as e:
        _LOGGER.error(f"Error in ComEd fetch_day_ahead_prices: {e}", exc_info=True)
        return None
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from ComEd Hourly Pricing API."""
    try:
        # Map area to endpoint if it's a valid ComEd area
        if area in ComEd.AREAS:
            endpoint = area
        else:
            # Default to 5minutefeed if area is not recognized
            _LOGGER.warning(f"Unrecognized ComEd area: {area}, defaulting to 5minutefeed")
            endpoint = ComEd.FIVE_MINUTE_FEED

        # Generate date ranges to try - ComEd uses 5-minute intervals
        # Ensure reference_time is not None to avoid TypeError
        current_time = reference_time if reference_time is not None else datetime.now(timezone.utc)
        date_ranges = generate_date_ranges(current_time, Source.COMED)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            url = f"{ComEd.BASE_URL}?type={endpoint}"

            # ComEd API doesn't use date parameters in the URL, but we log the date range for debugging
            _LOGGER.debug(f"Fetching ComEd data from URL: {url} for date range: {start_date.isoformat()} to {end_date.isoformat()}")

            response = None
            try:
                async with asyncio.timeout(60):
                    response = await client.fetch(url)
            except TimeoutError:
                _LOGGER.error("Timeout fetching ComEd data")
                continue  # Try next date range
            except Exception as e:
                _LOGGER.error(f"Error fetching ComEd data: {e}")
                continue  # Try next date range

            if not response:
                _LOGGER.warning(f"Empty response from ComEd API for date range: {start_date.isoformat()} to {end_date.isoformat()}")
                continue  # Try next date range

            # If we got a valid response, process it
            if response:
                break

        # If we've tried all date ranges and still have no data, return None
        if not response:
            _LOGGER.warning("No valid data found from ComEd after trying multiple date ranges")
            return None

        # Check if response is valid
        if isinstance(response, dict) and "error" in response:
            _LOGGER.error(f"Error response from ComEd API: {response.get('message', 'Unknown error')}")
            return None

        # Check if response is valid JSON
        try:
            # If response is already a string, try to parse it as JSON
            if isinstance(response, str):
                # First try standard JSON parsing
                json.loads(response)
            # If response is already parsed JSON (dict or list), no need to parse
        except json.JSONDecodeError:
            # If that fails, try to fix the malformed JSON
            try:
                # Add missing commas between properties
                fixed_json = re.sub(r'""', '","', response)
                # Fix array brackets if needed
                if not fixed_json.startswith('['):
                    fixed_json = '[' + fixed_json
                if not fixed_json.endswith(']'):
                    fixed_json = fixed_json + ']'
                json.loads(fixed_json)
                _LOGGER.debug("Successfully fixed malformed JSON from ComEd API")
                # Replace the response with the fixed JSON
                response = fixed_json
            except (json.JSONDecodeError, ValueError) as e:
                _LOGGER.error(f"Invalid JSON response from ComEd API: {e}")
                return None

        return {
            "raw_data": response,
            "endpoint": endpoint,
            "url": url
        }
    except Exception as e:
        _LOGGER.error(f"Failed to fetch data from ComEd API: {e}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from ComEd Hourly Pricing API."""
    if not data or "raw_data" not in data:
        return None

    try:
        # Initialize timezone service with area and config
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Get source timezone from API constants
        source_timezone = SourceTimezone.API_TIMEZONES.get(Source.COMED)
        _LOGGER.debug(f"Using source timezone {source_timezone} for ComEd")

        # Get current time
        now = reference_time or datetime.now(timezone.utc)
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
            "api_timezone": source_timezone
        }

        try:
            # Use the ComedParser to parse the data
            parser = ComedParser()

            # Extract metadata
            metadata = parser.extract_metadata(data)
            api_currency = metadata.get("currency", Currency.USD)

            # Parse hourly prices
            raw_hourly_prices = parser.parse_hourly_prices(data, area)

            if not raw_hourly_prices:
                _LOGGER.warning(f"No hourly prices parsed from ComEd data for area {area}")
                return None

            # Create raw prices array for reference
            for hour_str, price in raw_hourly_prices.items():
                try:
                    hour = int(hour_str.split(":")[0])
                    now_date = datetime.now().date()
                    hour_time = datetime.combine(now_date, time(hour=hour))
                    hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                    end_time = hour_time + timedelta(hours=1)

                    result["raw_prices"].append({
                        "start": hour_time.isoformat(),
                        "end": end_time.isoformat(),
                        "price": price
                    })
                except Exception as e:
                    _LOGGER.debug(f"Error adding raw price for hour {hour_str}: {e}")
                    continue

            # Convert hourly prices to proper timezone
            if raw_hourly_prices:
                converted_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_hourly_prices, source_timezone)

                # Apply price conversions (currency, VAT, etc.)
                for hour_str, price in converted_hourly_prices.items():
                    try:
                        converted_price = await async_convert_energy_price(
                            price=price,
                            from_unit=EnergyUnit.KWH,  # ComEd uses cents per kWh
                            to_unit=EnergyUnit.KWH,
                            from_currency=api_currency,
                            to_currency=currency,
                            vat=vat,
                            to_subunit=use_subunit,
                            session=session
                        )

                        result["hourly_prices"][hour_str] = converted_price
                    except Exception as e:
                        _LOGGER.debug(f"Error converting price for hour {hour_str}: {e}")
                        continue

                # Get current and next hour prices
                current_hour_key = tz_service.get_current_hour_key()
                if current_hour_key in result["hourly_prices"]:
                    result["current_price"] = result["hourly_prices"][current_hour_key]
                    result["raw_values"]["current_price"] = {
                        "raw": raw_hourly_prices.get(current_hour_key),
                        "unit": f"{api_currency}/{EnergyUnit.KWH}",
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
                        "unit": f"{api_currency}/{EnergyUnit.KWH}",
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
            _LOGGER.error(f"Error parsing ComEd data: {e}")
            return None

        return result
    except Exception as e:
        _LOGGER.error(f"Error processing ComEd data: {e}", exc_info=True)
        return None

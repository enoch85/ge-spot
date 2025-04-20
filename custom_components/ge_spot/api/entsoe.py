"""API handler for ENTSO-E Transparency Platform."""
import logging
from datetime import datetime, timezone, timedelta, time
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..timezone.timezone_utils import get_source_timezone, get_timezone_object
from ..const.sources import Source
from ..const.areas import AreaMapping
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import EntsoE
from ..utils.date_range import generate_date_ranges

# Document types for ENTSO-E API
DOCUMENT_TYPES = ["A44", "A62", "A65"]
from ..const.network import Network, ContentType
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.ENTSOE

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using ENTSO-E API."""
    client = ApiClient(session=session)
    try:
        # Settings
        use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS
        vat = config.get(Config.VAT, 0)

        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Check if the API was skipped due to missing API key
        if isinstance(raw_data, dict) and raw_data.get("skipped"):
            return raw_data

        # Process data
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session, config)

        # Add metadata
        if result:
            result["data_source"] = "ENTSO-E"
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency
            result["api_key_valid"] = True

        return result
    finally:
        if not session and client:
            await client.close()

from .base.data_fetch import create_skipped_response

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from ENTSO-E."""
    api_key = config.get(Config.API_KEY) or config.get("api_key")
    if not api_key:
        _LOGGER.debug("No API key provided for ENTSO-E, skipping")
        return create_skipped_response(Source.ENTSOE, "missing_api_key")

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Map our area code to ENTSO-E area code
    entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
    _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

    # Use custom headers for ENTSO-E API
    headers = {
        "User-Agent": Network.Defaults.USER_AGENT,
        "Accept": ContentType.XML,
        "Content-Type": ContentType.XML
    }

    # Generate date ranges to try
    # ENTSO-E sometimes has data for different time periods depending on the area
    date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)

    for start_date, end_date in date_ranges:
        # Format dates for ENTSO-E API (YYYYMMDDHHMM format)
        period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
        period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)

        # Try different document types
        for doc_type in DOCUMENT_TYPES:
            # Build query parameters
            params = {
                "securityToken": api_key,
                "documentType": doc_type,
                "in_Domain": entsoe_area,
                "out_Domain": entsoe_area,
                "periodStart": period_start,
                "periodEnd": period_end,
            }

            _LOGGER.debug(f"Trying ENTSO-E with document type {doc_type} and date range: {period_start} to {period_end}")

            # Sanitize params before logging to hide security token
            sanitized_params = sanitize_sensitive_data(params)
            _LOGGER.debug(f"ENTSO-E request params: {sanitized_params}")

            response = await client.fetch(
                BASE_URL,
                params=params,
                headers=headers,
                timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
            )

            if not response:
                _LOGGER.debug(f"ENTSO-E returned empty response for document type {doc_type} and date range {period_start} to {period_end}")
                continue

            _LOGGER.debug(f"ENTSO-E response type: {type(response)}")
            if isinstance(response, str):
                _LOGGER.debug(f"ENTSO-E response preview: {response[:200]}...")

            # Handle authentication errors
            if isinstance(response, dict) and not response:
                # Empty dictionary usually means HTTP error was encountered
                _LOGGER.error("ENTSO-E API authentication failed: Unauthorized. Check your API key.")
                return create_skipped_response(Source.ENTSOE, "invalid_api_key")

            # Check for authentication errors in string response
            if isinstance(response, str):
                if "Not authorized" in response:
                    _LOGGER.error("ENTSO-E API authentication failed: Not authorized. Check your API key.")
                    return create_skipped_response(Source.ENTSOE, "invalid_api_key")
                elif "No matching data found" in response:
                    # Try next document type
                    _LOGGER.debug(f"ENTSO-E returned 'No matching data found' for document type {doc_type} and date range {period_start} to {period_end}")
                    continue
                elif "Publication_MarketDocument" in response:
                    # We got a valid response with data
                    _LOGGER.info(f"Successfully fetched ENTSO-E data with document type {doc_type} for area {area}")
                    return response
                else:
                    # Unexpected response format, try next document type
                    _LOGGER.debug(f"ENTSO-E returned unexpected response format for document type {doc_type}")
                    continue
            elif isinstance(response, dict):
                # We got a valid response with data
                return response
            else:
                # Unexpected response type
                _LOGGER.debug(f"ENTSO-E returned unexpected response type for document type {doc_type} and date range {period_start} to {period_end}")
                continue

    # If we've tried all date ranges and still have no data, return a structured response
    _LOGGER.warning(f"ENTSO-E: No data found for area {area} after trying multiple date ranges")
    return {
        "hourly_prices": {},
        "raw_data": "No matching data found after trying multiple date ranges",
        "data_source": "ENTSO-E",
        "message": "No matching data found"
    }

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process XML data from ENTSO-E."""
    if not data:
        return None

    try:
        # Initialize timezone service with area and config to use area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Use default timezone for ENTSOE
        source_timezone = get_source_timezone(Source.ENTSOE)
        _LOGGER.debug(f"Using source timezone for ENTSO-E: {source_timezone}")

        # Ensure we have a valid timezone object, not just a string
        source_tz_obj = get_timezone_object(source_timezone)
        if not source_tz_obj:
            _LOGGER.error(f"Failed to get timezone object for {source_timezone}, falling back to UTC")
            source_tz_obj = timezone.utc

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
            # Use the EntsoeParser to parse hourly prices
            parser = EntsoeParser()

            # Extract metadata
            metadata = parser.extract_metadata(data)
            entsoe_currency = metadata.get("currency", Currency.EUR)

            # Parse hourly prices - may return a dict with both hourly_prices and tomorrow_hourly_prices
            parser_result = parser.parse_hourly_prices(data, area)
            
            # Check if the parser returned a dict with both hourly_prices and tomorrow_hourly_prices
            raw_hourly_prices = {}
            raw_tomorrow_hourly_prices = {}
            
            if isinstance(parser_result, dict) and "hourly_prices" in parser_result and "tomorrow_hourly_prices" in parser_result:
                # New format with separated hourly prices
                raw_hourly_prices = parser_result["hourly_prices"]
                raw_tomorrow_hourly_prices = parser_result["tomorrow_hourly_prices"]
                _LOGGER.info(f"Using separated today ({len(raw_hourly_prices)}) and tomorrow ({len(raw_tomorrow_hourly_prices)}) data")
            else:
                # Old format with just hourly prices
                raw_hourly_prices = parser_result
                _LOGGER.debug(f"Using legacy format hourly prices format")

            # Create raw prices array for reference from today's data
            for hour_str, price in raw_hourly_prices.items():
                # Check if hour_str is in ISO format (contains 'T')
                if "T" in hour_str:
                    try:
                        # Parse ISO format date
                        hour_time = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                        # Make it timezone-aware using HA timezone - explicitly pass source_timezone
                        hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                        end_time = hour_time + timedelta(hours=1)
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse ISO date: {hour_str} - {e}")
                        continue
                else:
                    # Original code for "HH:00" format
                    try:
                        hour = int(hour_str.split(":")[0])
                        # Create a timezone-aware datetime using HA timezone
                        now = datetime.now().date()
                        hour_time = datetime.combine(now, time(hour=hour))
                        # Make it timezone-aware using HA timezone - explicitly pass source_timezone
                        hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                        end_time = hour_time + timedelta(hours=1)
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse hour: {hour_str} - {e}")
                        continue

                # Store raw price
                result["raw_prices"].append({
                    "start": hour_time.isoformat(),
                    "end": end_time.isoformat(),
                    "price": price
                })

            # Convert hourly prices to area-specific timezone (or HA timezone) in a single step
            converted_prices = tz_service.normalize_hourly_prices(
                raw_hourly_prices, source_timezone)

            # Process each hour with price conversion
            for hour_str, price in converted_prices.items():
                # Apply price conversion
                converted_price = await async_convert_energy_price(
                    price=price,
                    from_unit=EnergyUnit.MWH,
                    to_unit="kWh",
                    from_currency=entsoe_currency,
                    to_currency=currency,
                    vat=vat,
                    to_subunit=use_subunit,
                    session=session
                )

                # Store converted price
                result["hourly_prices"][hour_str] = converted_price
                
            # Process tomorrow hourly prices if available
            if raw_tomorrow_hourly_prices:
                _LOGGER.debug(f"Raw tomorrow hourly prices with ISO timestamps: {list(raw_tomorrow_hourly_prices.items())[:5]} ({len(raw_tomorrow_hourly_prices)} total)")
                
                # Add raw prices for tomorrow as well
                for hour_str, price in raw_tomorrow_hourly_prices.items():
                    # Check if hour_str is in ISO format (contains 'T')
                    if "T" in hour_str:
                        try:
                            # Parse ISO format date
                            hour_time = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                            # Make it timezone-aware using HA timezone - explicitly pass source_timezone
                            hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                            end_time = hour_time + timedelta(hours=1)
                            
                            # Store raw price
                            result["raw_prices"].append({
                                "start": hour_time.isoformat(),
                                "end": end_time.isoformat(),
                                "price": price,
                                "tomorrow": True
                            })
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"Failed to parse ISO date in tomorrow data: {hour_str} - {e}")
                
                # Initialize tomorrow_hourly_prices in result if not there
                if "tomorrow_hourly_prices" not in result:
                    result["tomorrow_hourly_prices"] = {}
                    
                # Convert tomorrow hourly prices to area-specific timezone
                converted_tomorrow_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_tomorrow_hourly_prices, source_timezone)
                    
                # Apply price conversions for tomorrow prices
                for hour_str, price in converted_tomorrow_hourly_prices.items():
                    converted_price = await async_convert_energy_price(
                        price=price,
                        from_unit=EnergyUnit.MWH,
                        to_unit="kWh",
                        from_currency=entsoe_currency,
                        to_currency=currency,
                        vat=vat,
                        to_subunit=use_subunit,
                        session=session
                    )

                    result["tomorrow_hourly_prices"][hour_str] = converted_price

            # Get current and next hour prices
            current_hour_key = tz_service.get_current_hour_key()
            if current_hour_key in result["hourly_prices"]:
                result["current_price"] = result["hourly_prices"][current_hour_key]
                # Get original hour key from before conversion
                original_hour = int(current_hour_key.split(":")[0])
                current_dt = datetime.now().replace(hour=original_hour)
                current_dt = tz_service.converter.convert(current_dt, source_tz=source_timezone)
                original_hour_key = f"{current_dt.hour:02d}:00"

                result["raw_values"]["current_price"] = {
                    "raw": raw_hourly_prices.get(original_hour_key),
                    "unit": f"{entsoe_currency}/MWh",
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
                    "unit": f"{entsoe_currency}/MWh",
                    "final": result["next_hour_price"],
                    "currency": currency,
                    "vat_rate": vat
                }

            # Calculate statistics
            all_prices = list(result["hourly_prices"].values())
            if all_prices:
                result["day_average_price"] = sum(all_prices) / len(all_prices)
                result["peak_price"] = max(all_prices)
                result["off_peak_price"] = min(all_prices)

                # Raw value details for statistics
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
            _LOGGER.error(f"Error parsing ENTSO-E data: {e}")
            return None

        return result

    except ET.ParseError as e:
        _LOGGER.error(f"Error parsing ENTSO-E XML: {e}")
        return None
    except Exception as e:
        _LOGGER.error(f"Error processing ENTSO-E data: {e}", exc_info=True)
        return None

async def validate_api_key(api_key, area, session=None):
    """Validate an API key by making a test request."""
    try:
        # Create a simple configuration for validation
        config = {
            "area": area,
            "api_key": api_key
        }

        client = ApiClient(session=session)
        try:
            # Try to fetch data
            result = await _fetch_data(client, config, area, None)

            # Check if we got a valid response
            if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
                return True
            elif isinstance(result, dict) and result.get("hourly_prices") is not None:
                # Valid response with data
                return True
            elif isinstance(result, str) and "Not authorized" in result:
                return False
            elif isinstance(result, str) and "No matching data found" in result:
                # This is a valid key even if there's no data
                return True
            elif isinstance(result, dict) and result.get("skipped") and result.get("reason") == "invalid_api_key":
                return False
            elif isinstance(result, dict) and result.get("message") == "No matching data found":
                # Valid key but no data
                return True
            else:
                # Try one more direct test with a specific document type and date range
                _LOGGER.debug("Trying direct API key validation with specific parameters")

                # Use custom headers for ENTSO-E API
                headers = {
                    "User-Agent": Network.Defaults.USER_AGENT,
                    "Accept": ContentType.XML,
                    "Content-Type": ContentType.XML
                }

                # Map our area code to ENTSO-E area code
                entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)

                # Generate a standard date range for validation
                now = datetime.now(timezone.utc)
                date_ranges = generate_date_ranges(now, Source.ENTSOE, include_historical=False, include_future=False)
                start_date, end_date = date_ranges[0]  # Use just the first range for validation
                period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
                period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)

                # Try each document type
                for doc_type in DOCUMENT_TYPES:
                    params = {
                        "securityToken": api_key,
                        "documentType": doc_type,
                        "in_Domain": entsoe_area,
                        "out_Domain": entsoe_area,
                        "periodStart": period_start,
                        "periodEnd": period_end,
                    }

                    # Sanitize params before logging to hide security token
                    sanitized_params = sanitize_sensitive_data(params)
                    _LOGGER.debug(f"ENTSO-E validation params: {sanitized_params}")

                    response = await client.fetch(
                        BASE_URL,
                        params=params,
                        headers=headers,
                        timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                    )

                    if response and isinstance(response, str):
                        if "<Publication_MarketDocument" in response:
                            return True
                        elif "Not authorized" in response:
                            return False

                # If we've tried everything and still can't determine, assume it's invalid
                return False
        finally:
            if not session and client:
                await client.close()

    except Exception as e:
        _LOGGER.error(f"API key validation error: {e}")
        return False

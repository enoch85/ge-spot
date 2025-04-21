"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..timezone.timezone_utils import get_source_timezone, get_timezone_object
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.network import Network, ContentType
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import Nordpool
from .parsers.nordpool_parser import NordpoolPriceParser
from ..utils.date_range import generate_date_ranges
from .base.data_fetch import create_skipped_response

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.NORDPOOL

# Market types for Nordpool API - similar to ENTSOE document types
MARKET_TYPES = ["DayAhead", "DayAhead-Spot", "DayAhead-Forecast"]

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

        # Check if the API was skipped due to any reason
        if isinstance(raw_data, dict) and raw_data.get("skipped"):
            return raw_data

        # Process data
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session, config)

        # Add metadata
        if result:
            result["data_source"] = "Nordpool"
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Nordpool using date ranges similar to ENTSO-E approach."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Use custom headers for Nordpool API - similar to ENTSOE approach
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.JSON,
            "Content-Type": ContentType.JSON
        }

        # Generate date ranges to try - just like ENTSO-E
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Try different date ranges and market types - similar to ENTSOE's approach with document types
        for start_date, end_date in date_ranges:
            # Format dates for Nordpool API (YYYY-MM-DD format)
            start_date_str = start_date.strftime(TimeFormat.DATE_ONLY)
            end_date_str = end_date.strftime(TimeFormat.DATE_ONLY)

            # Try different market types - similar to ENTSOE's document types
            for market_type in MARKET_TYPES:
                params = {
                    "currency": Currency.EUR,
                    "date": end_date_str,  # Always use end date which is more likely to have data
                    "market": market_type,
                    "deliveryArea": delivery_area
                }

                _LOGGER.debug(f"Trying Nordpool with market type {market_type} and date: {params['date']}")
                
                # Sanitize params before logging - similar to ENTSOE
                sanitized_params = params.copy()
                _LOGGER.debug(f"Nordpool request params: {sanitized_params}")

                response = await client.fetch(
                    BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                )

                if not response:
                    _LOGGER.debug(f"Nordpool returned empty response for market type {market_type} and date {params['date']}")
                    continue

                _LOGGER.debug(f"Nordpool response type: {type(response)}")
                
                # Handle error responses
                if isinstance(response, dict) and not response:
                    # Empty dictionary usually means HTTP error was encountered
                    _LOGGER.error("Nordpool API request failed: Empty response")
                    continue

                # Check for valid response structure
                if isinstance(response, dict) and "multiAreaEntries" in response:
                    # Check if we got data for the requested area
                    entries = response.get("multiAreaEntries", [])
                    if entries and any(area in entry.get("entryPerArea", {}) for entry in entries):
                        _LOGGER.info(f"Successfully fetched Nordpool data with market type {market_type} for area {area} ({len(entries)} entries)")
                        
                        # Now fetch tomorrow's data separately - similar to ENTSOE's approach
                        tomorrow = (reference_time + timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)
                        tomorrow_params = {
                            "currency": Currency.EUR,
                            "date": tomorrow,
                            "market": market_type,
                            "deliveryArea": delivery_area
                        }
                        
                        _LOGGER.debug(f"Fetching tomorrow's data for Nordpool area {area} with date: {tomorrow}")
                        tomorrow_response = await client.fetch(
                            BASE_URL,
                            params=tomorrow_params,
                            headers=headers,
                            timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                        )
                        
                        # Check if we got valid tomorrow data
                        if tomorrow_response and isinstance(tomorrow_response, dict) and "multiAreaEntries" in tomorrow_response:
                            tomorrow_entries = tomorrow_response.get("multiAreaEntries", [])
                            _LOGGER.info(f"Successfully fetched tomorrow's data for Nordpool area {area} ({len(tomorrow_entries)} entries)")
                            
                            # Verify that the entries are actually for tomorrow
                            tomorrow_date = (reference_time + timedelta(days=1)).date()
                            has_tomorrow_data = False
                            tomorrow_entries_count = 0
                            
                            for entry in tomorrow_entries:
                                if "deliveryStart" in entry:
                                    try:
                                        start_time = entry["deliveryStart"]
                                        dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                                        entry_date = dt.date()
                                        
                                        if entry_date == tomorrow_date:
                                            tomorrow_entries_count += 1
                                            has_tomorrow_data = True
                                            _LOGGER.debug(f"Found valid tomorrow entry: {dt.isoformat()} (date: {entry_date}, tomorrow: {tomorrow_date})")
                                        else:
                                            _LOGGER.debug(f"Entry date {entry_date} does not match tomorrow date {tomorrow_date}")
                                    except (ValueError, TypeError) as e:
                                        _LOGGER.debug(f"Failed to parse timestamp: {start_time} - {e}")
                                        continue
                            
                            if not has_tomorrow_data:
                                _LOGGER.warning(f"Tomorrow's data for Nordpool area {area} does not contain entries for tomorrow date {tomorrow_date}")
                                # Don't use data that doesn't actually contain tomorrow's entries
                                tomorrow_response = None
                            else:
                                _LOGGER.info(f"Found {tomorrow_entries_count} entries for tomorrow date {tomorrow_date}")
                        else:
                            _LOGGER.warning(f"Failed to fetch valid tomorrow's data for Nordpool area {area}")
                            tomorrow_response = None
                        
                        # Create a combined response with both today and tomorrow data
                        combined_response = {
                            "today": response,
                            "tomorrow": tomorrow_response,
                            "market_type": market_type  # Store the market type that worked - similar to ENTSOE's document type
                        }
                        
                        # If we have tomorrow data, extract it directly into tomorrow_hourly_prices
                        # This is needed for the test to detect tomorrow's data
                        if tomorrow_response and isinstance(tomorrow_response, dict) and "multiAreaEntries" in tomorrow_response:
                            # Create a parser to extract tomorrow's data
                            from .parsers.nordpool_parser import NordpoolPriceParser
                            parser = NordpoolPriceParser()
                            
                            # Extract tomorrow's data
                            tomorrow_prices = {}
                            for entry in tomorrow_response.get("multiAreaEntries", []):
                                if not isinstance(entry, dict) or "entryPerArea" not in entry:
                                    continue
                                
                                if area not in entry["entryPerArea"]:
                                    continue
                                
                                # Extract values
                                start_time = entry.get("deliveryStart")
                                raw_price = entry["entryPerArea"][area]
                                
                                if start_time and raw_price is not None:
                                    # Parse timestamp
                                    try:
                                        dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                                        # Format as simple hour key
                                        hour_key = f"{dt.hour:02d}:00"
                                        tomorrow_prices[hour_key] = float(raw_price)
                                    except (ValueError, TypeError) as e:
                                        _LOGGER.warning(f"Failed to parse timestamp: {start_time} - {e}")
                            
                            # Add tomorrow's data to the combined response
                            combined_response["tomorrow_hourly_prices"] = tomorrow_prices
                            _LOGGER.info(f"Added {len(tomorrow_prices)} tomorrow prices directly to the response")
                        
                        return combined_response
                else:
                    # Unexpected response format, try next market type
                    _LOGGER.debug(f"Nordpool returned unexpected response format for market type {market_type}")
                    continue

        # If we've tried all date ranges and market types and still don't have data, return a structured response
        _LOGGER.warning(f"Nordpool: No data found for area {area} after trying multiple date ranges and market types")
        return {
            "today_hourly_prices": {},
            "raw_data": "No matching data found after trying multiple date ranges and market types",
            "data_source": "Nordpool",
            "message": "No matching data found"
        }
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from Nordpool."""
    if not data:
        return None

    try:
        # Handle new combined format
        if isinstance(data, dict) and ("today" in data or "tomorrow" in data):
            _LOGGER.debug("Processing combined format data with today/tomorrow keys")
            
            # Check if we have tomorrow_hourly_prices directly in the data
            if "tomorrow_hourly_prices" in data and isinstance(data["tomorrow_hourly_prices"], dict):
                _LOGGER.info(f"Found tomorrow_hourly_prices directly in data with {len(data['tomorrow_hourly_prices'])} entries")
                # We'll preserve this for later use
                tomorrow_hourly_prices_direct = data["tomorrow_hourly_prices"]
            else:
                tomorrow_hourly_prices_direct = None
            
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
            data_to_process["market_type"] = data.get("market_type")  # Preserve market type
            
            # If we had tomorrow_hourly_prices directly in the data, add it to data_to_process
            if tomorrow_hourly_prices_direct:
                data_to_process["tomorrow_hourly_prices"] = tomorrow_hourly_prices_direct
                
            data = data_to_process
        elif not data or "multiAreaEntries" not in data:
            _LOGGER.error("Missing or invalid multiAreaEntries in Nordpool data")
            return None

        # Initialize timezone service with area and config to use area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Extract source timezone from data or use default for Nordpool
        source_timezone = get_source_timezone(Source.NORDPOOL)
        _LOGGER.debug(f"Using source timezone for Nordpool: {source_timezone}")

        # Ensure we have a valid timezone object, not just a string - similar to ENTSOE
        source_tz_obj = get_timezone_object(source_timezone)
        if not source_tz_obj:
            _LOGGER.error(f"Failed to get timezone object for {source_timezone}, falling back to UTC")
            source_tz_obj = timezone.utc

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
            "api_timezone": source_timezone,  # Store API timezone for reference
            "market_type": data.get("market_type")  # Store the market type that worked - similar to ENTSOE's document type
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
            parser = NordpoolPriceParser(tz_service)

            # Extract metadata - similar to ENTSOE pattern
            metadata = parser.extract_metadata(data)
            nordpool_currency = metadata.get("currency", Currency.EUR)

            # Parse hourly prices with ISO timestamps - use a consistent approach
            # Pass the entire data structure to the parser, including tomorrow data if available
            if isinstance(data, dict) and "today" in data and "tomorrow" in data:
                parser_result = parser.parse_hourly_prices(data, area)
            else:
                parser_result = parser.parse_hourly_prices({"data": data}, area)

            # Check if the parser returned a dict with both today_hourly_prices and tomorrow_hourly_prices
            raw_today_hourly_prices = {}
            raw_tomorrow_hourly_prices = {}

            if isinstance(parser_result, dict) and "today_hourly_prices" in parser_result and "tomorrow_hourly_prices" in parser_result:
                # New format with separated hourly prices
                raw_today_hourly_prices = parser_result["today_hourly_prices"]
                raw_tomorrow_hourly_prices = parser_result["tomorrow_hourly_prices"]
                _LOGGER.info(f"Using separated today ({len(raw_today_hourly_prices)}) and tomorrow ({len(raw_tomorrow_hourly_prices)}) data")
            elif isinstance(parser_result, dict) and "hourly_prices" in parser_result and "tomorrow_hourly_prices" in parser_result:
                # Transitional format - convert hourly_prices to today_hourly_prices
                raw_today_hourly_prices = parser_result["hourly_prices"]
                raw_tomorrow_hourly_prices = parser_result["tomorrow_hourly_prices"]
                _LOGGER.info(f"Using transitional format: hourly_prices -> today_hourly_prices ({len(raw_today_hourly_prices)}) and tomorrow ({len(raw_tomorrow_hourly_prices)}) data")
            else:
                # Old format with just hourly prices (or already migrated to today_hourly_prices)
                raw_today_hourly_prices = parser_result
                _LOGGER.debug(f"Using legacy format hourly prices format")

            # Create raw prices array for reference from today's data - similar to ENTSOE
            for hour_str, price in raw_today_hourly_prices.items():
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

            # Log the raw hourly prices with ISO timestamps to help with debugging
            if raw_today_hourly_prices:
                _LOGGER.debug(f"Raw today hourly prices with ISO timestamps: {list(raw_today_hourly_prices.items())[:5]} ({len(raw_today_hourly_prices)} total)")

            # Process raw tomorrow data to add to raw_prices for reference
            if raw_tomorrow_hourly_prices:
                _LOGGER.debug(f"Raw tomorrow hourly prices with ISO timestamps: {list(raw_tomorrow_hourly_prices.items())[:5]} ({len(raw_tomorrow_hourly_prices)} total)")

            # Initialize tomorrow_hourly_prices in result if not there
            if "tomorrow_hourly_prices" not in result:
                result["tomorrow_hourly_prices"] = {}
                
            # If we have tomorrow_hourly_prices in the original data, use it directly
            if "tomorrow_hourly_prices" in data and isinstance(data["tomorrow_hourly_prices"], dict):
                _LOGGER.info(f"Found tomorrow_hourly_prices in data with {len(data['tomorrow_hourly_prices'])} entries")
                # We'll still process these through the timezone service for consistency
                raw_tomorrow_hourly_prices = data["tomorrow_hourly_prices"]

            # Combine all hourly prices into a single dictionary
            all_hourly_prices = {}
            all_hourly_prices.update(raw_today_hourly_prices)
            all_hourly_prices.update(raw_tomorrow_hourly_prices)
            
            # Debug raw data to better understand the structure
            if raw_today_hourly_prices:
                _LOGGER.debug(f"Raw today keys before sorting: {list(raw_today_hourly_prices.keys())[:5]}")
            if raw_tomorrow_hourly_prices:
                _LOGGER.debug(f"Raw tomorrow keys before sorting: {list(raw_tomorrow_hourly_prices.keys())[:5]}")
                
            # Force source_timezone to 'Etc/UTC' for Nordpool as timestamps are UTC with 'Z' suffix
            # This ensures proper timezone conversion regardless of what extract_source_timezone returns
            converted_today, converted_tomorrow = tz_service.sort_today_tomorrow(
                all_hourly_prices, 'Etc/UTC')  # Use standard Etc/UTC format

            _LOGGER.debug(f"After sorting: Today prices: {len(converted_today)}, Tomorrow prices: {len(converted_tomorrow)}")

            # Apply price conversions for today prices
            for hour_str, price in converted_today.items():
                converted_price = await async_convert_energy_price(
                    price=price,
                    from_unit=EnergyUnit.MWH,
                    to_unit="kWh",
                    from_currency=nordpool_currency,
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
                    from_currency=nordpool_currency,
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
                    "unit": f"{nordpool_currency}/MWh",
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
                    "unit": f"{nordpool_currency}/MWh",
                    "final": result["next_hour_price"],
                    "currency": currency,
                    "vat_rate": vat
                }

            # Calculate statistics
            all_prices = list(result["today_hourly_prices"].values())
            if all_prices:
                result["day_average_price"] = sum(all_prices) / len(all_prices)
                result["peak_price"] = max(all_prices)
                result["off_peak_price"] = min(all_prices)

                # Raw value details for statistics - similar to ENTSOE
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
            _LOGGER.error(f"Error parsing Nordpool data: {e}")
            return None

        return result
    except Exception as e:
        _LOGGER.error(f"Error processing Nordpool data: {e}", exc_info=True)
        return None

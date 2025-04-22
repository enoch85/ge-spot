"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone, timedelta, time
import asyncio
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.api import Aemo
from .parsers.aemo_parser import AemoParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

# Documentation about AEMO's API structure
"""
AEMO (Australian Energy Market Operator) API Details:
-------------------------------------------------------
Unlike European markets, AEMO provides real-time spot prices at 5-minute intervals
rather than daily ahead auctions. The integration works with a consolidated endpoint:

1. ELEC_NEM_SUMMARY - A comprehensive endpoint that contains:
   - Current spot prices for all regions
   - Detailed price information including regulation and contingency prices
   - Market notices

The API provides data for five regions across Australia:
- NSW1 - New South Wales
- QLD1 - Queensland
- SA1  - South Australia
- TAS1 - Tasmania
- VIC1 - Victoria

For more information, see: https://visualisations.aemo.com.au/
"""

# Add a note about AEMO's data structure
"""
AEMO provides real-time spot prices rather than day-ahead prices like European markets.
This implementation combines data from multiple AEMO endpoints:
1. Current spot prices from ELEC_NEM_SUMMARY
2. Historical prices from DAILY_PRICE
3. Forecast prices from PREDISPATCH_PRICE

The data is then combined to create a dataset that's compatible with the GE-Spot integration.
If there are missing hours, the fallback manager will try to fill them from other APIs.
"""

async def fetch_day_ahead_prices(
    source_type, config, area, currency, reference_time=None, hass=None, session=None
):  # pylint: disable=too-many-arguments
    """Fetch electricity prices using AEMO APIs.
    
    This function only fetches raw data from the API without any processing.
    Processing is handled by the data managers.
    
    Note: AEMO provides real-time spot prices rather than day-ahead prices.
    All necessary data is now available through the consolidated ELEC_NEM_SUMMARY endpoint.
    """
    client = ApiClient(session=session)
    try:
        # Validate area
        if area not in Aemo.REGIONS:
            _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
            return None

        # Get current time in Australia
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Fetch data from the consolidated ELEC_NEM_SUMMARY endpoint
        raw_data = await _fetch_summary_data(client, config, area, reference_time)

        if not raw_data:
            _LOGGER.error("Failed to fetch AEMO data")
            return None

        # Return simplified format with just raw data and metadata
        # This follows the new simplified API response format
        result = {
            "raw_data": raw_data,
            "api_timezone": "Australia/Sydney",  # AEMO API uses Australian Eastern Time
            "currency": Currency.AUD  # AEMO API returns prices in AUD
        }

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_summary_data(client, config, area, reference_time):
    """Fetch data from the consolidated AEMO endpoint."""
    try:
        # Generate date ranges to try - AEMO uses 5-minute intervals
        date_ranges = generate_date_ranges(reference_time, Source.AEMO)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Format the time for AEMO API - use start_date which is rounded to 5-minute intervals
            formatted_time = start_date.strftime("%Y%m%dT%H%M%S")

            params = {
                "time": formatted_time,
            }

            _LOGGER.debug(f"Fetching AEMO data with params: {params}")
            response = await client.fetch(Aemo.SUMMARY_URL, params=params)

            # If we got a valid response, return it
            if response and Aemo.SUMMARY_ARRAY in response:
                _LOGGER.info(f"Successfully fetched AEMO data with time: {formatted_time}")
                return response
            else:
                _LOGGER.debug(f"No valid data from AEMO for time: {formatted_time}, trying next range")

        # If we've tried all ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from AEMO after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error fetching AEMO data: {e}")
        return None

async def _process_summary_data(
    data, area, currency, vat, use_subunit, reference_time, hass, session, config
):  # pylint: disable=too-many-arguments,too-many-locals
    """Process data from the consolidated AEMO ELEC_NEM_SUMMARY endpoint."""
    # Improved validation to match the old implementation's clarity
    if not data or Aemo.SUMMARY_ARRAY not in data:
        _LOGGER.error("Invalid or missing data from AEMO API")
        return None

    try:
        # Initialize timezone service with area and config for area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug("Initialized TimezoneService for area %s with timezone %s",
                     area, tz_service.area_timezone or tz_service.ha_timezone)
        source_timezone = tz_service.extract_source_timezone(None, Source.AEMO)

        # Get current time in proper timezone
        now = reference_time or datetime.now(timezone.utc)
        if hass:
            now = tz_service.convert_to_ha_timezone(now)

        # Initialize result structure with proper keys
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

        # Raw hourly prices for further processing
        raw_hourly_prices = {}

        # AEMO uses AUD as currency
        api_currency = Currency.AUD

        # Process main array data
        if Aemo.SUMMARY_ARRAY in data:
            # Extract pricing data for target region
            found_entries = []
            for entry in data[Aemo.SUMMARY_ARRAY]:
                if entry.get(Aemo.REGION_FIELD) == area:
                    settlement_time = entry.get(Aemo.SETTLEMENT_DATE_FIELD)
                    price = entry.get(Aemo.PRICE_FIELD)

                    if not settlement_time or price is None:
                        continue

                    try:
                        dt = tz_service.parse_timestamp(settlement_time, source_timezone)
                        # AEMO uses 5-minute intervals, but we need hourly for GE-Spot
                        # Store using standard hour format (HH:00)
                        hour_str = f"{dt.hour:02d}:00"
                        minute_str = f"{dt.hour:02d}:{dt.minute:02d}"

                        # Store price
                        price = float(price)
                        raw_hourly_prices[hour_str] = price

                        # Add to raw prices
                        result["raw_prices"].append({
                            "start": dt.isoformat(),
                            "end": (dt + timedelta(hours=1)).isoformat(),
                            "price": price,
                            "source": "current",
                            "interval": minute_str
                        })

                        # Keep track of entries we found
                        found_entries.append({
                            "hour": hour_str,
                            "minute": minute_str,
                            "timestamp": dt,
                            "price": price
                        })
                    except (ValueError, TypeError) as e:
                        _LOGGER.error(f"Error parsing AEMO timestamp {settlement_time}: {e}")
                        continue

            # Log found entries for debugging
            if found_entries:
                _LOGGER.debug(f"Found {len(found_entries)} data points for region {area}: {found_entries}")
            else:
                _LOGGER.warning(f"No data points found for region {area} in ELEC_NEM_SUMMARY")

        # Process prices array data for additional validation and details
        if Aemo.PRICES_ARRAY in data:
            for entry in data[Aemo.PRICES_ARRAY]:
                if entry.get(Aemo.REGION_FIELD) == area:
                    # Extract detailed price components (from old implementation)
                    # Store additional price details in attributes
                    result["price_details"] = {
                        "RRP": entry.get("RRP"),
                        "RAISE_REG": entry.get("RAISEREGRRP"),
                        "LOWER_REG": entry.get("LOWERREGRRP"),
                        "RAISE_5MIN": entry.get("RAISE5MINRRP"),
                        "LOWER_5MIN": entry.get("LOWER5MINRRP"),
                        # Add additional fields if available
                        "RAISE_60SEC": entry.get("RAISE60SECRRP"),
                        "LOWER_60SEC": entry.get("LOWER60SECRRP"),
                        "RAISE_6SEC": entry.get("RAISE6SECRRP"),
                        "LOWER_6SEC": entry.get("LOWER6SECRRP"),
                        "RAISE_1SEC": entry.get("RAISE1SECRRP"),
                        "LOWER_1SEC": entry.get("LOWER1SECRRP")
                    }

                    # Use RRP as a fallback price if needed
                    if Aemo.RRP_FIELD in entry:
                        # Use this price as a fallback/verification
                        # Since this price should match the one in the main array
                        # but we'll use it if the main array didn't have a price
                        hour_key = tz_service.get_current_hour_key()
                        if hour_key not in raw_hourly_prices:
                            price = float(entry[Aemo.RRP_FIELD])
                            raw_hourly_prices[hour_key] = price

                            # Create timestamp for this hour
                            now_date = datetime.now().date()
                            hour = int(hour_key.split(":")[0])
                            hour_time = datetime.combine(now_date, time(hour=hour))
                            hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)

                            # Add to raw prices
                            result["raw_prices"].append({
                                "start": hour_time.isoformat(),
                                "end": (hour_time + timedelta(hours=1)).isoformat(),
                                "price": price,
                                "source": "prices_array"
                            })

                    # We only need the details from the first matching entry
                    break

        # Log a warning if we have fewer than 1 hour of data
        if len(raw_hourly_prices) < 1:
            _LOGGER.warning(f"No hourly prices available for {area}. Missing hours will be checked in fallback sources.")
            return None

        # Process collected raw hourly prices
        if raw_hourly_prices:
            # Convert hourly prices to area-specific timezone (or HA timezone) in a single step
            converted_hourly_prices = tz_service.normalize_hourly_prices(
                raw_hourly_prices, source_timezone)

            # Apply price conversions
            for hour_str, price in converted_hourly_prices.items():
                # Convert price with proper units and currency
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

            # Get current hour price
            current_hour_key = tz_service.get_current_hour_key()
            _LOGGER.debug(f"Current hour key from timezone service: {current_hour_key}")

            # Since we're using the simple hour format (HH:00), make sure our key matches
            if current_hour_key in result["hourly_prices"]:
                _LOGGER.debug(f"Found exact match for current hour key: {current_hour_key}")
                result["current_price"] = result["hourly_prices"][current_hour_key]
                result["raw_values"]["current_price"] = {
                    "raw": raw_hourly_prices.get(current_hour_key),
                    "unit": f"{api_currency}/MWh",
                    "final": result["current_price"],
                    "currency": currency,
                    "vat_rate": vat
                }
            else:
                # Try to extract the hour from the key for a different format match
                try:
                    current_hour = int(current_hour_key.split(":")[0])
                    # Try alternate formats
                    alternate_keys = [
                        f"{current_hour:02d}:00",
                        f"{current_hour:02d}:30"  # AEMO often uses half-hour intervals
                    ]

                    _LOGGER.debug(f"Trying alternate hour keys: {alternate_keys}")
                    for alt_key in alternate_keys:
                        if alt_key in result["hourly_prices"]:
                            _LOGGER.debug(f"Found match with alternate key: {alt_key}")
                            result["current_price"] = result["hourly_prices"][alt_key]
                            result["raw_values"]["current_price"] = {
                                "raw": raw_hourly_prices.get(alt_key),
                                "unit": f"{api_currency}/MWh",
                                "final": result["current_price"],
                                "currency": currency,
                                "vat_rate": vat
                            }
                            break
                except (ValueError, IndexError):
                    _LOGGER.warning(f"Failed to parse hour from current hour key: {current_hour_key}")

            # Calculate next hour key
            current_hour = int(current_hour_key.split(":")[0])
            next_hour = (current_hour + 1) % 24
            next_hour_key = f"{next_hour:02d}:00"

            _LOGGER.debug(f"Next hour key calculated as: {next_hour_key}")

            # Check if next hour price exists
            if next_hour_key in result["hourly_prices"]:
                _LOGGER.debug(f"Found exact match for next hour key: {next_hour_key}")
                result["next_hour_price"] = result["hourly_prices"][next_hour_key]
                result["raw_values"]["next_hour_price"] = {
                    "raw": raw_hourly_prices.get(next_hour_key),
                    "unit": f"{api_currency}/MWh",
                    "final": result["next_hour_price"],
                    "currency": currency,
                    "vat_rate": vat
                }
            else:
                # Try alternate formats for next hour too
                try:
                    alternate_keys = [
                        f"{next_hour:02d}:30"  # AEMO often uses half-hour intervals
                    ]

                    _LOGGER.debug(f"Trying alternate next hour keys: {alternate_keys}")
                    for alt_key in alternate_keys:
                        if alt_key in result["hourly_prices"]:
                            _LOGGER.debug(f"Found match with alternate next hour key: {alt_key}")
                            result["next_hour_price"] = result["hourly_prices"][alt_key]
                            result["raw_values"]["next_hour_price"] = {
                                "raw": raw_hourly_prices.get(alt_key),
                                "unit": f"{api_currency}/MWh",
                                "final": result["next_hour_price"],
                                "currency": currency,
                                "vat_rate": vat
                            }
                            break
                except (ValueError, IndexError):
                    _LOGGER.warning(f"Failed to parse hour for next hour calculation")

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
        _LOGGER.error("Error processing AEMO data: %s", e, exc_info=True)
        return None

async def _process_combined_data(
    combined_data, area, currency, vat, use_subunit, reference_time, hass, session, config
):  # pylint: disable=too-many-arguments,too-many-locals
    """Process combined data from multiple AEMO sources."""
    if not combined_data:
        _LOGGER.error("No combined data available from AEMO")
        return None

    try:
        # Initialize timezone service with area and config for area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug("Initialized TimezoneService for area %s with timezone %s",
                     area, tz_service.area_timezone or tz_service.ha_timezone)
        source_timezone = tz_service.extract_source_timezone(None, Source.AEMO)

        # Get current time in proper timezone
        now = reference_time or datetime.now(timezone.utc)
        if hass:
            now = tz_service.convert_to_ha_timezone(now)

        # Initialize result structure with proper keys
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
            # Use the AemoParser to parse hourly prices
            parser = AemoParser()

            # Extract metadata
            metadata = parser.extract_metadata(combined_data)
            api_currency = metadata.get("currency", Currency.AUD)

            # Add data sources to result
            result["data_sources"] = metadata.get("data_sources", [])

            # Add price details if available
            if "price_details" in metadata:
                result["price_details"] = metadata["price_details"]

            # Parse hourly prices
            raw_hourly_prices = parser.parse_hourly_prices(combined_data, area)

            # Create raw prices array for reference
            for hour_str, price in raw_hourly_prices.items():
                # Create a timezone-aware datetime
                hour = int(hour_str.split(":")[0])
                now_date = datetime.now().date()
                hour_time = datetime.combine(now_date, time(hour=hour))
                # Make it timezone-aware
                hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                end_time = hour_time + timedelta(hours=1)

                # Determine source (for debugging)
                source = "unknown"
                if hour_str in raw_hourly_prices:
                    # Try to determine which source this price came from
                    if isinstance(result, dict) and "data_sources" in result:
                        if "current" in result["data_sources"]:
                            source = "current"
                        elif "historical" in result["data_sources"]:
                            source = "historical"
                        elif "forecast" in result["data_sources"]:
                            source = "forecast"

                # Store raw price
                result["raw_prices"].append({
                    "start": hour_time.isoformat(),
                    "end": end_time.isoformat(),
                    "price": price,
                    "source": source
                })

            # Log a warning if we have fewer than 12 hours of data
            if len(raw_hourly_prices) < 12:
                _LOGGER.warning(f"Only {len(raw_hourly_prices)} hours of data available for {area}. Missing hours will be checked in fallback sources.")

            # Process collected raw hourly prices
            if raw_hourly_prices:
                # Convert hourly prices to area-specific timezone (or HA timezone) in a single step
                converted_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_hourly_prices, source_timezone)

                # Apply price conversions
                for hour_str, price in converted_hourly_prices.items():
                    # Convert price with proper units and currency
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

                # Calculate next hour key
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
            _LOGGER.error(f"Error parsing AEMO data: {e}")
            return None

        return result

    except Exception as e:
        _LOGGER.error("Error processing AEMO data: %s", e, exc_info=True)
        return None

# Function removed: _fill_missing_hours
# We no longer fill in missing hours with estimates.
# Instead, we return incomplete data and let the fallback manager
# try to fill in missing hours from other sources.

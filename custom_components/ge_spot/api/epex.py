"""API handler for EPEX SPOT."""
import logging
from datetime import datetime, timezone, timedelta, time
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from .parsers.epex_parser import EpexParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.epexspot.com/en/market-results"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using EPEX SPOT API."""
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
            result["data_source"] = "EPEX SPOT"
            result["last_updated"] = datetime.now(timezone.utc).isoformat()
            result["currency"] = currency

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from EPEX SPOT."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Generate date ranges to try
    date_ranges = generate_date_ranges(reference_time, Source.EPEX)

    # EPEX uses trading_date and delivery_date
    # We'll use the first range (today to tomorrow) as our primary range
    today_start, tomorrow_end = date_ranges[0]

    # Format dates for the query
    trading_date = today_start.strftime("%Y-%m-%d")
    delivery_date = tomorrow_end.strftime("%Y-%m-%d")

    params = {
        "market_area": area,
        "auction": "MRC",
        "trading_date": trading_date,
        "delivery_date": delivery_date,
        "modality": "Auction",
        "sub_modality": "DayAhead",
        "data_mode": "table"
    }

    _LOGGER.debug(f"Fetching EPEX with params: {params}")

    response = await client.fetch(BASE_URL, params=params)

    # If the first attempt fails, try with other date ranges
    if not response and len(date_ranges) > 1:
        for start_date, end_date in date_ranges[1:]:
            trading_date = start_date.strftime("%Y-%m-%d")
            delivery_date = end_date.strftime("%Y-%m-%d")

            params.update({
                "trading_date": trading_date,
                "delivery_date": delivery_date
            })

            _LOGGER.debug(f"Retrying EPEX with alternate dates - trading: {trading_date}, delivery: {delivery_date}")

            response = await client.fetch(BASE_URL, params=params)
            if response:
                _LOGGER.info(f"Successfully fetched EPEX data with alternate dates")
                break

    return response

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session, config):
    """Process data from EPEX SPOT."""
    if not data or not isinstance(data, str):
        _LOGGER.error("No valid HTML data received from EPEX")
        return None

    try:
        # Get current time
        now = reference_time or datetime.now(timezone.utc)

        # Initialize timezone service with area and config to use area-specific timezone
        tz_service = TimezoneService(hass, area, config)
        _LOGGER.debug(f"Initialized TimezoneService for area {area} with timezone {tz_service.area_timezone or tz_service.ha_timezone}")

        # Extract source timezone from EPEX data or use default
        source_timezone = tz_service.extract_source_timezone(data, Source.EPEX)

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
            # Use the EpexParser to parse hourly prices
            parser = EpexParser()

            # Extract metadata
            metadata = parser.extract_metadata(data)
            api_currency = metadata.get("currency", Currency.EUR)
            from_unit = EnergyUnit.MWH

            # Add metadata to result
            if "delivery_date" in metadata:
                result["delivery_date"] = metadata["delivery_date"]

            if "market_area" in metadata:
                result["market_area"] = metadata["market_area"]

            # Parse hourly prices
            raw_hourly_prices = parser.parse_hourly_prices(data, area)

            # Create raw prices array for reference
            for hour_str, price in raw_hourly_prices.items():
                try:
                    try:
                        # Parse the hour string
                        hour = int(hour_str.split(":")[0])

                        # Get base date
                        now_date = datetime.now().date()

                        # Use the utility function to normalize the hour value
                        from ..timezone.timezone_utils import normalize_hour_value
                        normalized_hour, adjusted_date = normalize_hour_value(hour, now_date)

                        # Create the datetime with the normalized values
                        hour_time = datetime.combine(adjusted_date, time(hour=normalized_hour))
                    except ValueError as e:
                        # Skip invalid hours
                        _LOGGER.warning(f"Skipping invalid hour value in EPEX data: {hour_str} - {e}")
                        continue

                    # Make it timezone-aware
                    hour_time = tz_service.converter.convert(hour_time, source_tz=source_timezone)
                    end_time = hour_time + timedelta(hours=1)

                    # Store raw price
                    result["raw_prices"].append({
                        "start": hour_time.isoformat(),
                        "end": end_time.isoformat(),
                        "price": price
                    })
                except ValueError as e:
                    _LOGGER.warning(f"Skipping invalid hour value in EPEX data: {hour_str} - {e}")

            # Now convert hourly prices to area-specific timezone (or HA timezone) in a single step
            if raw_hourly_prices:
                converted_hourly_prices = tz_service.normalize_hourly_prices(
                    raw_hourly_prices, source_timezone)

                # Apply price conversions (currency, VAT, etc.)
                for hour_str, price in converted_hourly_prices.items():
                    # Convert price
                    converted_price = await async_convert_energy_price(
                        price=price,
                        from_unit=from_unit,
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
                        "unit": f"{api_currency}/{from_unit}",
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
                        "unit": f"{api_currency}/{from_unit}",
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
            _LOGGER.error(f"Error parsing EPEX data: {e}")
            return None

        return result

    except Exception as e:
        _LOGGER.error(f"Error processing EPEX data: {e}", exc_info=True)
        return None

#!/usr/bin/env python3
"""
Manual full chain test for OMIE API (Spain/Portugal).

This script performs an end-to-end test of the OMIE API integration:
1. Fetches real data from the OMIE API
2. Parses the raw data
3. Normalizes timezones
4. Applies currency conversion (optional)
5. Validates and displays the results

Usage:
    python omie_full_chain.py [area] [--date YYYY-MM-DD] [--debug]

    area: Optional area code (ES, PT)
          Defaults to ES if not provided
    --date: Optional date to fetch data for (format: YYYY-MM-DD)
            Defaults to today if not provided
    --debug: Enable detailed debug logging
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
import asyncio
import pytz
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from custom_components.ge_spot.api.omie import OmieAPI
from custom_components.ge_spot.api.parsers.omie_parser import OmieParser  # Import the parser
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.const.config import Config  # Added import
from custom_components.ge_spot.const.time import TimezoneReference  # Added import

# OMIE areas and their corresponding timezones
OMIE_AREA_TIMEZONES = {
    "ES": "Europe/Madrid",
    "PT": "Europe/Lisbon",
}


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test OMIE API integration")
    parser.add_argument(
        "area",
        nargs="?",
        default="ES",
        choices=OMIE_AREA_TIMEZONES.keys(),
        help="Area code (ES, PT)",
    )
    parser.add_argument(
        "--date", default=None, help="Date to fetch data for (format: YYYY-MM-DD, default: today)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable detailed debug logging")
    args = parser.parse_args()

    # Configure logging level
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    area = args.area
    reference_date_str = args.date
    local_tz_name = OMIE_AREA_TIMEZONES.get(area, "Europe/Madrid")
    local_tz = pytz.timezone(local_tz_name)

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(local_tz).date()  # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, "%Y-%m-%d")
            target_date = ref_date_obj.date()
            # OMIE API might use local time, create reference in local time
            reference_time = local_tz.localize(ref_date_obj.replace(hour=12, minute=0, second=0))
            logger.info(
                f"Using reference date: {reference_date_str} (reference time: {reference_time})"
            )
        except ValueError:
            logger.error(
                f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format."
            )
            return 1
    else:
        # Default to now in the local timezone if no date specified
        reference_time = datetime.now(local_tz)

    logger.info(f"\n===== OMIE API Full Chain Test for {area} =====\n")

    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    tz_config = {Config.TIMEZONE_REFERENCE: TimezoneReference.LOCAL_AREA}
    tz_service = TimezoneService(hass=None, area=area, config=tz_config)  # Correct initialization
    # Use str() to correctly log the timezone name
    logger.info(
        f"Timezone service initialized for area: {area} using target timezone: {str(tz_service.target_timezone)}"
    )

    # Initialize the API client
    api = OmieAPI(config={})  # OMIE API might not need specific config

    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching OMIE data for area: {area}")
        # Adjust fetch call based on OmieAPI's expected parameters
        raw_data_dict = await api.fetch_raw_data(area=area, reference_time=reference_time)

        if not raw_data_dict:
            logger.error("Error: Failed to fetch data from OMIE API")
            return 1

        logger.debug(f"Raw data keys: {list(raw_data_dict.keys())}")
        log_data = {}
        for k, v in raw_data_dict.items():
            # Handle potentially large data like CSV content
            if k == "raw_data" and isinstance(v, str):  # Check specifically for raw_data string
                log_data[k] = v[:100] + "..." if len(v) > 100 else v
            elif isinstance(v, (str, list, dict)) and len(str(v)) > 300:
                log_data[k] = str(v)[:300] + "..."
            else:
                log_data[k] = v
        logger.debug(f"Raw data content (summary): {json.dumps(log_data, indent=2)}")

        # Step 2: Parse the raw data
        logger.info("\nParsing the fetched raw data...")
        parser = OmieParser()  # Instantiate the parser
        parsed_data = parser.parse(raw_data_dict)  # Call the parser's parse method

        if not parsed_data or not parsed_data.get("interval_raw"):  # Changed from hourly_raw
            logger.error("Error: Parser did not return valid data or interval_raw prices.")
            logger.error(f"Available keys: {list(parsed_data.keys()) if parsed_data else 'None'}")
            # Log raw response if helpful
            if "raw_data" in raw_data_dict:
                logger.debug(
                    f"--- Raw Text Data --- START ---\n{raw_data_dict['raw_data']}\n--- Raw Text Data --- END ---"
                )
            return 1

        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        # Use 'source' key as set by the parser
        logger.info(f"Source: {parsed_data.get('source')}")
        logger.info(f"Area: {area}")
        original_currency = parsed_data.get("currency", Currency.EUR)
        logger.info(f"Currency: {original_currency}")
        # Use 'timezone' key as set by the parser
        source_timezone = parsed_data.get("timezone")
        logger.info(f"API Timezone: {source_timezone}")

        # OMIE provides hourly interval prices
        interval_raw_prices = parsed_data.get("interval_raw", {})  # Changed from hourly_raw
        # This check should now reflect the parser's output
        if not interval_raw_prices:
            logger.error("Error: No interval prices found in the parsed data *after parsing step*.")
            return 1

        logger.info(
            f"Found {len(interval_raw_prices)} raw interval prices (before timezone normalization)"
        )
        logger.debug(f"Raw interval prices sample: {dict(list(interval_raw_prices.items())[:5])}")

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {local_tz_name}...")
        # Use normalize_interval_prices to handle intervals consistently
        # Note: OMIE is hourly only, so this will show 24 intervals per day
        normalized_prices = tz_service.converter.normalize_interval_prices(
            interval_prices=interval_raw_prices,  # Changed from hourly_raw_prices
            source_timezone_str=source_timezone,
            preserve_date=True,  # Ensure date is included in keys for split_into_today_tomorrow
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        logger.info(f"Expected: ~48 intervals (OMIE provides hourly data only)")
        logger.debug(f"Normalized prices sample: {dict(list(normalized_prices.items())[:5])}")

        # Step 4: Currency and Unit conversion (EUR/MWh -> EUR/kWh)
        target_currency = Currency.EUR  # OMIE uses EUR
        logger.info(f"\nConverting units from {original_currency}/MWh to {target_currency}/kWh...")

        converted_prices = {}
        for time_key, price_info in normalized_prices.items():
            price_mwh = price_info["price"] if isinstance(price_info, dict) else price_info
            # No currency conversion needed, just unit conversion
            price_kwh = price_mwh / 1000
            converted_prices[time_key] = price_kwh
            # Ensure structure is consistent for display
            if isinstance(normalized_prices[time_key], dict):
                normalized_prices[time_key]["converted_kwh"] = price_kwh
            else:
                normalized_prices[time_key] = {"price": price_mwh, "converted_kwh": price_kwh}

        logger.debug(
            f"Final prices sample ({target_currency}/kWh): {dict(list(converted_prices.items())[:5])}"
        )

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Unit: {original_currency}/MWh")
        logger.info(f"Converted Unit: {target_currency}/kWh")

        # Split into today/tomorrow based on the *local* target date
        today_prices, tomorrow_prices = tz_service.converter.split_into_today_tomorrow(
            normalized_prices
        )

        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nHourly Prices (formatted time in target timezone: {local_tz_name}):")
        logger.info(f"{'Hour':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 45)

        for hour_key, price_data in sorted(all_display_prices.items()):
            original_val = price_data["price"]
            converted_val = price_data["converted_kwh"]
            logger.info(f"{hour_key:<10} {original_val:<15.4f} {converted_val:<15.6f}")

        # Step 6: Validate data completeness (OMIE usually provides today and tomorrow)
        today_hour_range = tz_service.get_today_range()
        tomorrow_hour_range = tz_service.get_tomorrow_range()

        today_hours_found = set(today_prices.keys())
        tomorrow_hours_found = set(tomorrow_prices.keys())

        today_complete = today_hours_found.issuperset(today_hour_range)
        tomorrow_complete = tomorrow_hours_found.issuperset(tomorrow_hour_range)

        logger.info(f"\nData completeness check (Target Timezone: {local_tz_name}):")
        logger.info(
            f"Today ({target_date}): {len(today_hours_found)}/{len(today_hour_range)} hours {'✓' if today_complete else '⚠'}"
        )
        logger.info(
            f"Tomorrow ({target_date + timedelta(days=1)}): {len(tomorrow_hours_found)}/{len(tomorrow_hour_range)} hours {'✓' if tomorrow_complete else '⚠'}"
        )

        if not today_complete:
            missing_today = set(today_hour_range) - today_hours_found
            logger.warning(f"Missing today hours: {', '.join(sorted(missing_today))}")

        if not tomorrow_complete:
            # Check if it's before typical publication time (e.g. 13:00 local time)
            now_local = datetime.now(local_tz)
            if (
                now_local.hour >= 13 or reference_date_str
            ):  # If specific date requested, expect full data
                missing_tomorrow = set(tomorrow_hour_range) - tomorrow_hours_found
                logger.warning(f"Missing tomorrow hours: {', '.join(sorted(missing_tomorrow))}")
            else:
                logger.info("Tomorrow's data might not be available yet.")

        # Basic check: Did we get full data for today?
        if today_complete:
            logger.info("\nTest completed successfully (found complete data for today)!")
            return 0
        else:
            logger.error(
                f"\nTest failed: Incomplete price data found for today ({target_date}). Found {len(today_hours_found)}/{len(today_hour_range)} hours."
            )
            return 1

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1
    finally:
        # Ensure the session is closed if OmieAPI uses aiohttp
        if hasattr(api, "_session") and api._session and not api._session.closed:
            await api._session.close()
            logger.debug("Closed aiohttp session.")


if __name__ == "__main__":
    print("Starting OMIE API full chain test...")
    # Ensure asyncio event loop is managed correctly
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))

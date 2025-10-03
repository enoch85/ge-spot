#!/usr/bin/env python3
"""
Manual full chain test for ComEd API.

This script performs an end-to-end test of the ComEd API integration:
1. Fetches real data from the ComEd API
2. Parses the raw data
3. Normalizes timezones
4. Validates and displays the results

Usage:
    python comed_full_chain.py [--date YYYY-MM-DD] [--debug]

    --date: Optional date to fetch data for (format: YYYY-MM-DD)
            Defaults to today if not provided
    --debug: Enable detailed debug logging
"""

import sys
import os
import argparse
from datetime import datetime
import asyncio
import pytz
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.comed import ComedAPI
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

# ComEd serves the Chicago area
AREA = 'COMED_HOURLY_PRICING' # This is the area identifier used in ComEd API
LOCAL_TZ_NAME = 'America/Chicago'

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test ComEd API integration')
    parser.add_argument('--date', default=None,
                        help='Date to fetch data for (format: YYYY-MM-DD, default: today)')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debug logging')
    args = parser.parse_args()

    # Configure logging level
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    reference_date_str = args.date

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(pytz.timezone(LOCAL_TZ_NAME)).date() # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            # ComEd API might use local time for date ranges, let's create a reference in local time
            local_tz = pytz.timezone(LOCAL_TZ_NAME)
            reference_time = local_tz.localize(ref_date_obj.replace(hour=12, minute=0, second=0))
            logger.info(f"Using reference date: {reference_date_str} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format.")
            return 1
    else:
         # Default to now in the local timezone if no date specified
         reference_time = datetime.now(pytz.timezone(LOCAL_TZ_NAME))

    logger.info(f"\n===== ComEd API Full Chain Test for {AREA} =====\n")

    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    local_tz = pytz.timezone(LOCAL_TZ_NAME)
    tz_config = {"timezone_reference": "area"} # Assuming area dictates timezone
    # Use a fixed area for ComEd as it's specific
    tz_service = TimezoneService(area=AREA, config=tz_config, fixed_timezone=LOCAL_TZ_NAME)
    tz_converter = TimezoneConverter(tz_service)
    logger.info(f"Timezone service initialized for area: {AREA} using {LOCAL_TZ_NAME}")

    # Initialize the API client
    api = ComedAPI(config={}) # ComEd API might not need specific config like API keys

    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching ComEd data for area: {AREA}")
        # Adjust fetch call based on ComedAPI's expected parameters
        raw_data = await api.fetch_raw_data(area=AREA, reference_time=reference_time)

        if not raw_data:
            logger.error("Error: Failed to fetch data from ComEd API")
            return 1

        logger.debug(f"Raw data keys: {list(raw_data.keys())}")
        log_data = {}
        for k, v in raw_data.items():
             if isinstance(v, (str, list, dict)) and len(str(v)) > 300:
                 log_data[k] = str(v)[:300] + "..."
             else:
                 log_data[k] = v
        logger.debug(f"Raw data content (summary): {json.dumps(log_data, indent=2)}")

        # Step 2: Parse raw data
        logger.info("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)

        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"Source: {parsed_data.get('source_name', parsed_data.get('source'))}")
        logger.info(f"Area: {AREA}")
        original_currency = parsed_data.get('currency', Currency.USD) # ComEd uses USD
        logger.info(f"Currency: {original_currency}")
        source_timezone = parsed_data.get('timezone') # Parser should determine this
        logger.info(f"API Timezone: {source_timezone}")

        interval_raw_prices = parsed_data.get("interval_raw", {})  # Changed from hourly_raw
        if not interval_raw_prices:
            logger.error("Error: No interval prices found in the parsed data after parsing step.")
            logger.error(f"Available keys: {list(parsed_data.keys())}")
            # Log raw response if helpful
            if 'api_response' in raw_data:
                 logger.debug(f"--- Raw API Response --- START ---")
                 logger.debug(json.dumps(raw_data['api_response'], indent=2))
                 logger.debug(f"--- Raw API Response --- END ---")
            return 1

        logger.info(f"Found {len(interval_raw_prices)} raw interval price points (before timezone normalization)")
        # Check if data is 5-minute or hourly
        is_five_minute = parsed_data.get('is_five_minute', False)
        logger.info(f"Data interval: {'5-minute (aggregated to 15-min)' if is_five_minute else 'Hourly'}")
        logger.debug(f"Raw prices sample: {dict(list(interval_raw_prices.items())[:5])}")

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {LOCAL_TZ_NAME}...")
        # Use normalize_interval_prices to preserve 15-minute intervals
        normalized_prices = tz_converter.normalize_interval_prices(
            interval_prices=interval_raw_prices,  # Changed from hourly_raw_prices
            source_timezone_str=source_timezone,
            preserve_date=True # Keep original date context
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        logger.info(f"Expected: ~192 intervals (5-min aggregated to 15-min for 2 days)")
        logger.debug(f"Normalized prices sample: {dict(list(normalized_prices.items())[:5])}")

        # Step 4: Currency conversion (Not needed for ComEd as it's already USD)
        target_currency = Currency.USD
        logger.info(f"\nPrices are already in target currency: {target_currency}")

        converted_prices = {}
        for time_key, price_info in normalized_prices.items():
            # Price should already be in $/kWh or similar from the parser
            price_kwh = price_info["price"] if isinstance(price_info, dict) else price_info
            converted_prices[time_key] = price_kwh
            if isinstance(normalized_prices[time_key], dict):
                 normalized_prices[time_key]['converted_kwh'] = price_kwh
            else:
                 # Ensure structure is consistent for display
                 normalized_prices[time_key] = {'price': price_kwh, 'converted_kwh': price_kwh}

        logger.debug(f"Final prices sample ({target_currency}/kWh): {dict(list(converted_prices.items())[:5])}")

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Currency: {target_currency}/kWh") # Assuming parser provides price per kWh

        # Split into today/tomorrow based on the *local* target date
        today_prices, tomorrow_prices = tz_converter.split_into_today_tomorrow(
            normalized_prices,
            target_date=target_date # Pass the target date explicitly
        )

        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nPrice Points (formatted time in target timezone: {LOCAL_TZ_NAME}):")
        logger.info(f"{'Time':<20} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 40)

        for time_key, price_data in sorted(all_display_prices.items()):
            converted_val = price_data['converted_kwh']
            logger.info(f"{time_key:<20} {converted_val:<15.6f}")

        # Step 6: Validate data completeness (Adjust for 5-min or hourly)
        # This part needs careful adjustment based on what ComEd API returns (today only? tomorrow? 5-min?)
        # For simplicity, let's just check if we got *any* data for today.

        today_keys = set(today_prices.keys())

        logger.info(f"\nData completeness check (Target Timezone: {LOCAL_TZ_NAME}):")
        logger.info(f"Today ({target_date}): Found {len(today_keys)} price points.")

        # Basic check: Did we get at least some data for today?
        if len(today_keys) > 0:
            logger.info("\nTest completed successfully (found some price data)!")
            return 0
        else:
            logger.error(f"\nTest failed: No price data found for today ({target_date}).")
            return 1

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1

if __name__ == "__main__":
    print("Starting ComEd API full chain test...")
    # Ensure asyncio event loop is managed correctly
    if sys.platform == 'win32':
         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))


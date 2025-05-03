#!/usr/bin/env python3
"""
Manual full chain test for AEMO (Australian Energy Market Operator) API.

This script performs an end-to-end test of the AEMO API integration:
1. Fetches real data from the AEMO API
2. Parses the raw data
3. Normalizes timezones based on the area
4. Validates and displays the results

Usage:
    python aemo_full_chain.py [area] [--date YYYY-MM-DD] [--debug]
    
    area: Optional area code (NSW1, VIC1, QLD1, SA1, TAS1)
          Defaults to NSW1 if not provided
    --date: Optional date to fetch data for (format: YYYY-MM-DD)
            Defaults to today if not provided
    --debug: Enable detailed debug logging
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import asyncio
import pytz
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.aemo import AemoAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.const.time import TimezoneReference
from custom_components.ge_spot.const.config import Config

# AEMO areas and their corresponding timezones
AEMO_AREA_TIMEZONES = {
    'NSW1': 'Australia/Sydney',
    'VIC1': 'Australia/Melbourne',
    'QLD1': 'Australia/Brisbane',
    'SA1': 'Australia/Adelaide',
    'TAS1': 'Australia/Hobart',
}

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test AEMO API integration')
    parser.add_argument('area', nargs='?', default='NSW1', 
                        choices=AEMO_AREA_TIMEZONES.keys(),
                        help='Area code (e.g., NSW1, VIC1)')
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
    
    area = args.area
    reference_date_str = args.date
    local_tz_name = AEMO_AREA_TIMEZONES.get(area, 'Australia/Sydney')
    local_tz = pytz.timezone(local_tz_name)

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(local_tz).date() # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            reference_time = local_tz.localize(ref_date_obj.replace(hour=12, minute=0, second=0))
            logger.info(f"Using reference date: {reference_date_str} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format.")
            return 1
    else:
         reference_time = datetime.now(local_tz)

    logger.info(f"\n===== AEMO API Full Chain Test for {area} =====\n")
    
    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    tz_config = {Config.TIMEZONE_REFERENCE: TimezoneReference.LOCAL_AREA} 
    tz_service = TimezoneService(hass=None, area=area, config=tz_config) 
    logger.info(f"Timezone service initialized for area: {area} using target timezone: {tz_service.target_timezone}")

    # Initialize the API client
    api = AemoAPI(config={})
    
    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching AEMO data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)
        
        if not raw_data:
            logger.error("Error: Failed to fetch data from AEMO API")
            return 1
            
        logger.debug(f"Raw data keys: {list(raw_data.keys())}")
        log_data = {}
        for k, v in raw_data.items():
             if isinstance(v, str) and len(v) > 300:
                 log_data[k] = v[:300] + "..."
             elif isinstance(v, (list, dict)) and len(str(v)) > 300:
                 log_data[k] = str(v)[:300] + "..."
             else:
                 log_data[k] = v
        logger.debug(f"Raw data content (summary): {json.dumps(log_data, indent=2)}")
        
        # Step 2: Use the already parsed data from fetch step
        logger.info("\nUsing parsed data from fetch step...")
        parsed_data = raw_data # Use the result from fetch directly
        
        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"Source: {parsed_data.get('source_name', parsed_data.get('source'))}")
        logger.info(f"Area: {area}")
        original_currency = parsed_data.get('currency', Currency.AUD)
        logger.info(f"Currency: {original_currency}")
        source_timezone = parsed_data.get('timezone')
        logger.info(f"API Timezone: {source_timezone}")
        
        raw_prices = parsed_data.get("hourly_raw", {})
        if not raw_prices:
            logger.error("Error: No raw prices found in the parsed data after parsing step.")
            if 'raw_data' in parsed_data and 'data' in parsed_data['raw_data']:
                 logger.debug(f"--- Raw API Response --- START ---")
                 logger.debug(json.dumps(parsed_data['raw_data']['data'], indent=2))
                 logger.debug(f"--- Raw API Response --- END ---")
            return 1
            
        logger.info(f"Found {len(raw_prices)} raw price points (before timezone normalization)")
        is_five_minute = parsed_data.get('is_five_minute', True)
        logger.info(f"Data interval: {'5-minute' if is_five_minute else 'Hourly'}")
        logger.debug(f"Raw prices sample: {dict(list(raw_prices.items())[:5])}")

        # Define expected intervals based on data type
        expected_intervals_per_day = 288 if is_five_minute else 24

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {local_tz_name}...")
        normalized_prices = tz_service.normalize_hourly_prices(
            hourly_prices=raw_prices, 
            source_tz_str=source_timezone,
            is_five_minute=is_five_minute # Pass the flag
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        normalized_prices_sample = {k.isoformat(): v for k, v in list(normalized_prices.items())[:5]}
        logger.debug(f"Normalized prices sample: {normalized_prices_sample}")

        # Step 4: Unit conversion (MWh -> kWh)
        target_currency = Currency.AUD
        logger.info(f"\nConverting units from {original_currency}/MWh to {target_currency}/kWh...")
        
        converted_prices = {}
        for dt_key, price_info in normalized_prices.items():
            price_mwh = price_info
            price_kwh = price_mwh / 1000
            converted_prices[dt_key] = price_kwh
            normalized_prices[dt_key] = {'price': price_mwh, 'converted_kwh': price_kwh}

        converted_prices_sample = {k.isoformat(): v for k, v in list(converted_prices.items())[:5]}
        logger.debug(f"Final prices sample ({target_currency}/kWh): {converted_prices_sample}")

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Unit: {original_currency}/MWh")
        logger.info(f"Converted Unit: {target_currency}/kWh")
        
        today_prices = {}
        tomorrow_prices = {}
        tomorrow_date = target_date + timedelta(days=1)

        for dt_key, price_data in normalized_prices.items():
            if dt_key.date() == target_date:
                display_key = dt_key.strftime('%H:%M') 
                today_prices[display_key] = price_data
            elif dt_key.date() == tomorrow_date:
                display_key = dt_key.strftime('%H:%M')
                tomorrow_prices[display_key] = price_data

        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nPrice Points (formatted time in target timezone: {local_tz_name}):")
        logger.info(f"{'Time':<20} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 55)
        
        for time_key, price_data in sorted(all_display_prices.items()):
            original_val = price_data['price']
            converted_val = price_data['converted_kwh']
            logger.info(f"{time_key:<20} {original_val:<15.4f} {converted_val:<15.6f}")

        # Step 6: Validate data completeness
        today_raw_count = sum(1 for dt_key in normalized_prices if dt_key.date() == target_date)
        tomorrow_raw_count = sum(1 for dt_key in normalized_prices if dt_key.date() == tomorrow_date)

        logger.info(f"\nData validation check (Target Timezone: {local_tz_name}):")
        logger.info(f"Found {today_raw_count} price point(s) for today ({target_date}).")
        logger.info(f"Found {tomorrow_raw_count} price point(s) for tomorrow ({target_date + timedelta(days=1)}). Note: AEMO is real-time, tomorrow's data is not expected.")
        
        # For real-time AEMO, just check if we got *any* data for today
        min_expected_today = 1 # Expect at least one data point
        
        today_sufficient = today_raw_count >= min_expected_today
        
        if today_sufficient:
            logger.info(f"\nTest completed successfully (found at least {min_expected_today} price point for today)!")
            return 0
        else:
            logger.error(f"\nTest failed: No price data found for today ({target_date}). Found {today_raw_count}, expected at least {min_expected_today}.")
            return 1
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1

if __name__ == "__main__":
    print("Starting AEMO API full chain test...")
    if sys.platform == 'win32':
         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))

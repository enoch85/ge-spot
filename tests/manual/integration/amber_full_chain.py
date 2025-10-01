#!/usr/bin/env python3
"""
Manual full chain test for Amber API (Australia).

This script performs an end-to-end test of the Amber API integration:
1. Fetches real data from the Amber API
2. Parses the raw data
3. Normalizes timezones
4. Applies currency conversion (if needed)
5. Validates and displays the results

Usage:
    python amber_full_chain.py [area] [api_key] [--date YYYY-MM-DD] [--debug]
    
    area: Optional area code (e.g., NSW, VIC, QLD, SA, TAS)
          Defaults to NSW if not provided
    api_key: Optional Amber API key
             Can also be provided via AMBER_API_KEY environment variable
    --date: Optional date to fetch data for (format: YYYY-MM-DD)
            Defaults to today if not provided
    --debug: Enable detailed debug logging
"""

import sys
import os
import argparse
import getpass
from datetime import datetime, timezone, timedelta
import asyncio
import pytz
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.amber import AmberAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService # Keep for potential future use
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

# Amber areas roughly map to AEMO areas/timezones
AMBER_AREA_TIMEZONES = {
    'NSW': 'Australia/Sydney',
    'VIC': 'Australia/Melbourne',
    'QLD': 'Australia/Brisbane',
    'SA': 'Australia/Adelaide',
    'TAS': 'Australia/Hobart',
}

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Amber API integration')
    parser.add_argument('area', nargs='?', default='NSW', 
                        choices=AMBER_AREA_TIMEZONES.keys(),
                        help='Area code (e.g., NSW, VIC)')
    parser.add_argument('api_key', nargs='?', default=None,
                        help='Amber API key (optional if environment variable is set)')
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
    local_tz_name = AMBER_AREA_TIMEZONES.get(area, 'Australia/Sydney')
    local_tz = pytz.timezone(local_tz_name)

    # Get API key from arguments, environment, or prompt
    api_key = args.api_key or os.environ.get("AMBER_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your Amber API key: ")
        
    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(local_tz).date() # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            # Amber API likely uses local time, create reference in local time
            reference_time = local_tz.localize(ref_date_obj.replace(hour=12, minute=0, second=0))
            logger.info(f"Using reference date: {reference_date_str} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format.")
            return 1
    else:
         # Default to now in the local timezone if no date specified
         reference_time = datetime.now(local_tz)

    logger.info(f"\n===== Amber API Full Chain Test for {area} =====\n")
    
    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    tz_config = {"timezone_reference": "area"} # Assuming area dictates timezone
    tz_service = TimezoneService(area=area, config=tz_config, fixed_timezone=local_tz_name)
    tz_converter = TimezoneConverter(tz_service)
    logger.info(f"Timezone service initialized for area: {area} using {local_tz_name}")

    # Initialize the API client with the API key
    api = AmberAPI(config={"api_key": api_key})
    
    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching Amber data for area: {area}")
        # Adjust fetch call based on AmberAPI's expected parameters
        raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)
        
        if not raw_data:
            logger.error("Error: Failed to fetch data from Amber API")
            return 1
            
        # Log raw data summary
        if isinstance(raw_data, list):
            logger.debug(f"Received {len(raw_data)} data points in list")
            if raw_data:
                logger.debug(f"First raw data point sample: {json.dumps(raw_data[0], indent=2)}")
        elif isinstance(raw_data, dict):
             logger.debug(f"Raw data keys: {list(raw_data.keys())}")
             log_data = {}
             for k, v in raw_data.items():
                 if isinstance(v, (str, list, dict)) and len(str(v)) > 300:
                     log_data[k] = str(v)[:300] + "..."
                 else:
                     log_data[k] = v
             logger.debug(f"Raw data content (summary): {json.dumps(log_data, indent=2)}")
        else:
             logger.debug(f"Raw data type: {type(raw_data)}, content (truncated): {str(raw_data)[:300]}...")

        # Step 2: Parse raw data
        logger.info("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)
        
        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"Source: {parsed_data.get('source_name', parsed_data.get('source'))}")
        logger.info(f"Area: {area}")
        original_currency = parsed_data.get('currency', Currency.AUD)
        logger.info(f"Currency: {original_currency}")
        source_timezone = parsed_data.get('timezone') # Parser should determine this
        logger.info(f"API Timezone: {source_timezone}")
        
        # Amber provides prices per kWh, often in 30-min or 5-min intervals
        raw_prices = parsed_data.get("raw_prices", {}) # Assuming parser returns raw prices here
        if not raw_prices:
            logger.error("Error: No raw prices found in the parsed data after parsing step.")
            return 1
            
        logger.info(f"Found {len(raw_prices)} raw price points (before timezone normalization)")
        # Amber interval can vary, check if parser provides info
        is_five_minute = parsed_data.get('is_five_minute', False) 
        is_thirty_minute = parsed_data.get('is_thirty_minute', False)
        interval_desc = "5-minute" if is_five_minute else ("30-minute" if is_thirty_minute else "Hourly")
        logger.info(f"Data interval: {interval_desc}")
        logger.debug(f"Raw prices sample: {dict(list(raw_prices.items())[:5])}")

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {local_tz_name}...")
        # Use normalize_interval_prices to preserve 15-minute intervals
        normalized_prices = tz_converter.normalize_interval_prices(
            interval_prices=raw_prices, # Pass the raw prices
            source_timezone_str=source_timezone,
            preserve_date=True # Keep original date context
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        logger.info(f"Expected: Depends on Amber API interval (possibly 30-min or hourly)")
        logger.debug(f"Normalized prices sample: {dict(list(normalized_prices.items())[:5])}")

        # Step 4: Unit/Currency conversion (Amber is usually AUD/kWh, so only structure adjustment needed)
        target_currency = Currency.AUD
        logger.info(f"\nPrices are already in target currency/unit: {target_currency}/kWh")
        
        converted_prices = {}
        for time_key, price_info in normalized_prices.items():
            price_kwh = price_info["price"] if isinstance(price_info, dict) else price_info
            converted_prices[time_key] = price_kwh
            # Ensure structure is consistent for display
            if isinstance(normalized_prices[time_key], dict):
                 normalized_prices[time_key]['converted_kwh'] = price_kwh
            else:
                 normalized_prices[time_key] = {'price': price_kwh, 'converted_kwh': price_kwh}

        logger.debug(f"Final prices sample ({target_currency}/kWh): {dict(list(converted_prices.items())[:5])}")

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Currency/Unit: {target_currency}/kWh")
        
        # Split into today/tomorrow based on the *local* target date
        today_prices, tomorrow_prices = tz_converter.split_into_today_tomorrow(
            normalized_prices, 
            target_date=target_date # Pass the target date explicitly
        )
        
        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nPrice Points (formatted time in target timezone: {local_tz_name}):")
        logger.info(f"{'Time':<20} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 40)
        
        for time_key, price_data in sorted(all_display_prices.items()):
            converted_val = price_data['converted_kwh']
            logger.info(f"{time_key:<20} {converted_val:<15.6f}")

        # Step 6: Validate data completeness (Adjust for interval)
        today_keys = set(today_prices.keys())
        tomorrow_keys = set(tomorrow_prices.keys())
        
        # Expected intervals per day
        if is_five_minute:
            expected_intervals_per_day = 288
        elif is_thirty_minute:
            expected_intervals_per_day = 48
        else: # Assume hourly if not specified
            expected_intervals_per_day = 24
            
        logger.info(f"\nData completeness check (Target Timezone: {local_tz_name}):")
        logger.info(f"Today ({target_date}): Found {len(today_keys)}/{expected_intervals_per_day} price points.")
        logger.info(f"Tomorrow ({target_date + timedelta(days=1)}): Found {len(tomorrow_keys)}/{expected_intervals_per_day} price points.")
        
        # Basic check: Did we get a reasonable amount of data for today?
        # Amber might provide forecast data, but let's focus on getting *some* data for today.
        min_expected_today = expected_intervals_per_day // 4 # Expect at least a quarter of the day
        
        today_sufficient = len(today_keys) >= min_expected_today
        
        if today_sufficient:
            logger.info(f"\nTest completed successfully (found at least {min_expected_today} price points for today)!")
            return 0
        else:
            logger.error(f"\nTest failed: Insufficient price data found for today ({target_date}). Found {len(today_keys)}, expected at least {min_expected_today}.")
            return 1
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1
    finally:
        # Clean up resources if needed (e.g., close aiohttp session if used directly)
        pass 

if __name__ == "__main__":
    print("Starting Amber API full chain test...")
    # Ensure asyncio event loop is managed correctly
    if sys.platform == 'win32':
         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))

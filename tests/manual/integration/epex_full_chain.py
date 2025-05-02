#!/usr/bin/env python3
"""
Manual full chain test for EPEX (European Power Exchange) API.

This script performs an end-to-end test of the EPEX API integration:
1. Fetches real data from the EPEX API
2. Parses the raw data
3. Normalizes timezones
4. Applies currency conversion
5. Validates and displays the results

Usage:
    python epex_full_chain.py [area] [--date YYYY-MM-DD] [--debug]
    
    area: Optional area code (FR, DE-LU, AT, BE, CH, GB, NL)
          Defaults to DE-LU if not provided
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
from custom_components.ge_spot.api.epex import EpexAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

# EPEX areas and their corresponding timezones (approximations)
EPEX_AREA_TIMEZONES = {
    'FR': 'Europe/Paris',
    'DE-LU': 'Europe/Berlin', # CET
    'AT': 'Europe/Vienna',   # CET
    'BE': 'Europe/Brussels', # CET
    'CH': 'Europe/Zurich',   # CET
    'GB': 'Europe/London',   # WET/WEST
    'NL': 'Europe/Amsterdam',# CET
}

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test EPEX API integration')
    parser.add_argument('area', nargs='?', default='DE-LU', 
                        choices=EPEX_AREA_TIMEZONES.keys(),
                        help='Area code (e.g., FR, DE-LU)')
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
    local_tz_name = EPEX_AREA_TIMEZONES.get(area, 'Europe/Berlin')
    local_tz = pytz.timezone(local_tz_name)

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(local_tz).date() # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            # EPEX API might use local time, create reference in local time
            reference_time = local_tz.localize(ref_date_obj.replace(hour=12, minute=0, second=0))
            logger.info(f"Using reference date: {reference_date_str} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format.")
            return 1
    else:
         # Default to now in the local timezone if no date specified
         reference_time = datetime.now(local_tz)

    logger.info(f"\n===== EPEX API Full Chain Test for {area} =====\n")
    
    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    tz_config = {"timezone_reference": "area"} # Assuming area dictates timezone
    tz_service = TimezoneService(area=area, config=tz_config, fixed_timezone=local_tz_name)
    tz_converter = TimezoneConverter(tz_service)
    logger.info(f"Timezone service initialized for area: {area} using {local_tz_name}")

    # Initialize the API client
    api = EpexAPI(config={}) # EPEX API might not need specific config
    
    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching EPEX data for area: {area}")
        # Adjust fetch call based on EpexAPI's expected parameters
        raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)
        
        if not raw_data:
            logger.error("Error: Failed to fetch data from EPEX API")
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
        original_currency = parsed_data.get('currency', Currency.EUR) # EPEX usually EUR, except GB
        if area == 'GB':
            original_currency = Currency.GBP
        logger.info(f"Currency: {original_currency}")
        source_timezone = parsed_data.get('timezone') # Parser should determine this
        logger.info(f"API Timezone: {source_timezone}")
        
        # EPEX provides prices per MWh, usually hourly
        hourly_raw_prices = parsed_data.get("hourly_raw", {}) # Assuming parser returns raw prices here
        if not hourly_raw_prices:
            logger.error("Error: No hourly prices found in the parsed data after parsing step.")
            # Log raw response if helpful
            if 'api_response' in raw_data:
                 logger.debug(f"--- Raw API Response --- START ---")
                 logger.debug(json.dumps(raw_data['api_response'], indent=2))
                 logger.debug(f"--- Raw API Response --- END ---")
            return 1
            
        logger.info(f"Found {len(hourly_raw_prices)} raw hourly prices (before timezone normalization)")
        logger.debug(f"Raw hourly prices sample: {dict(list(hourly_raw_prices.items())[:5])}")

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {local_tz_name}...")
        # Use the timezone converter
        normalized_prices = tz_converter.normalize_hourly_prices(
            hourly_prices=hourly_raw_prices,
            source_timezone_str=source_timezone,
            preserve_date=True # Keep original date context
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        logger.debug(f"Normalized prices sample: {dict(list(normalized_prices.items())[:5])}")

        # Step 4: Currency and Unit conversion (e.g., EUR/MWh -> EUR/kWh or GBP/MWh -> GBP/kWh)
        target_currency = original_currency # Target currency is same as source for EPEX
        logger.info(f"\nConverting units from {original_currency}/MWh to {target_currency}/kWh...")
        
        converted_prices = {}
        for time_key, price_info in normalized_prices.items():
            price_mwh = price_info["price"] if isinstance(price_info, dict) else price_info
            # No currency conversion needed, just unit conversion
            price_kwh = price_mwh / 1000
            converted_prices[time_key] = price_kwh
            # Ensure structure is consistent for display
            if isinstance(normalized_prices[time_key], dict):
                 normalized_prices[time_key]['converted_kwh'] = price_kwh
            else:
                 normalized_prices[time_key] = {'price': price_mwh, 'converted_kwh': price_kwh}

        logger.debug(f"Final prices sample ({target_currency}/kWh): {dict(list(converted_prices.items())[:5])}")

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Unit: {original_currency}/MWh")
        logger.info(f"Converted Unit: {target_currency}/kWh")
        
        # Split into today/tomorrow based on the *local* target date
        today_prices, tomorrow_prices = tz_converter.split_into_today_tomorrow(
            normalized_prices, 
            target_date=target_date # Pass the target date explicitly
        )
        
        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nHourly Prices (formatted time in target timezone: {local_tz_name}):")
        logger.info(f"{'Hour':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 45)
        
        for hour_key, price_data in sorted(all_display_prices.items()):
            original_val = price_data['price']
            converted_val = price_data['converted_kwh']
            logger.info(f"{hour_key:<10} {original_val:<15.4f} {converted_val:<15.6f}")

        # Step 6: Validate data completeness (EPEX usually provides today and tomorrow)
        today_hour_range = tz_service.get_today_range()
        tomorrow_hour_range = tz_service.get_tomorrow_range()
        
        today_hours_found = set(today_prices.keys())
        tomorrow_hours_found = set(tomorrow_prices.keys())
        
        today_complete = today_hours_found.issuperset(today_hour_range)
        tomorrow_complete = tomorrow_hours_found.issuperset(tomorrow_hour_range)
        
        logger.info(f"\nData completeness check (Target Timezone: {local_tz_name}):")
        logger.info(f"Today ({target_date}): {len(today_hours_found)}/{len(today_hour_range)} hours {'✓' if today_complete else '⚠'}")
        logger.info(f"Tomorrow ({target_date + timedelta(days=1)}): {len(tomorrow_hours_found)}/{len(tomorrow_hour_range)} hours {'✓' if tomorrow_complete else '⚠'}")
        
        if not today_complete:
            missing_today = set(today_hour_range) - today_hours_found
            logger.warning(f"Missing today hours: {', '.join(sorted(missing_today))}")
            
        if not tomorrow_complete:
            # Check if it's before typical publication time (e.g., 13:00 local time)
            now_local = datetime.now(local_tz)
            if now_local.hour >= 13 or reference_date_str: # If specific date requested, expect full data
                missing_tomorrow = set(tomorrow_hour_range) - tomorrow_hours_found
                logger.warning(f"Missing tomorrow hours: {', '.join(sorted(missing_tomorrow))}")
            else:
                 logger.info("Tomorrow's data might not be available yet.")

        # Basic check: Did we get full data for today?
        if today_complete:
            logger.info("\nTest completed successfully (found complete data for today)!")
            return 0
        else:
            logger.error(f"\nTest failed: Incomplete price data found for today ({target_date}). Found {len(today_hours_found)}/{len(today_hour_range)} hours.")
            return 1
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1
    finally:
        # Clean up resources if needed (e.g., close aiohttp session if used directly)
        pass

if __name__ == "__main__":
    print("Starting EPEX API full chain test...")
    # Ensure asyncio event loop is managed correctly
    if sys.platform == 'win32':
         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))

#!/usr/bin/env python3
"""
Manual full chain test for ENTSO-E API.

This script performs an end-to-end test of the ENTSO-E API integration:
1. Fetches real data from the ENTSO-E API
2. Parses the raw data
3. Normalizes timezones based on the area
4. Applies currency conversion
5. Validates and displays the results

Usage:
    python entsoe_full_chain.py [area] [api_key] [--date YYYY-MM-DD] [--debug]

    area: Optional area code (e.g., SE1, SE2, SE3, SE4, FI, DK1, etc.)
          Defaults to FI if not provided
    api_key: Optional ENTSO-E API key
             Can also be provided via ENTSOE_API_KEY environment variable
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
from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

# Common ENTSO-E areas
COMMON_AREAS = [
    'SE1', 'SE2', 'SE3', 'SE4',  # Sweden
    'FI',                        # Finland
    'DK1', 'DK2',                # Denmark
    'NO1', 'NO2', 'NO3', 'NO4', 'NO5',  # Norway
    'EE', 'LV', 'LT',            # Baltic states
    'DE_LU',                     # Germany and Luxembourg
    'NL',                        # Netherlands
    'BE',                        # Belgium
    'FR',                        # France
    'ES',                        # Spain
    'PT',                        # Portugal
    'IT_NORD', 'IT_CNOR', 'IT_CSUD', 'IT_SUD',  # Italy
    'GB'                         # Great Britain
]

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test ENTSO-E API integration')
    parser.add_argument('area', nargs='?', default='FI',
                        help=f'Area code (e.g., {", ".join(COMMON_AREAS[:5])})')
    parser.add_argument('api_key', nargs='?', default=None,
                        help='ENTSO-E API key (optional if environment variable is set)')
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

    # Get API key from arguments, environment, or prompt
    api_key = args.api_key or os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your ENTSO-E API key: ")

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now().date()
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            reference_time = ref_date_obj.replace(
                hour=12, minute=0, second=0
            ).astimezone(timezone.utc)
            logger.info(f"Using reference date: {reference_date_str} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format.")
            return 1

    logger.info(f"\n===== ENTSO-E API Full Chain Test for {area} =====\n")

    # Initialize timezone service based on area
    logger.info("Setting up timezone service...")
    local_tz_name = 'Europe/Brussels'
    if area.startswith('FI'):
        local_tz_name = 'Europe/Helsinki'
    elif area.startswith('SE'):
        local_tz_name = 'Europe/Stockholm'
    elif area.startswith('DK'):
        local_tz_name = 'Europe/Copenhagen'
    elif area.startswith('NO'):
        local_tz_name = 'Europe/Oslo'
    elif area in ['EE']:
        local_tz_name = 'Europe/Tallinn'
    elif area in ['LV']:
        local_tz_name = 'Europe/Riga'
    elif area in ['LT']:
        local_tz_name = 'Europe/Vilnius'
    elif area == 'GB':
        local_tz_name = 'Europe/London'

    local_tz = pytz.timezone(local_tz_name)
    tz_config = {"timezone_reference": "area"}
    tz_service = TimezoneService(area=area, config=tz_config)
    tz_converter = TimezoneConverter(tz_service)
    logger.info(f"Timezone service initialized for area: {area} using {local_tz_name}")

    # Initialize the API client with the API key
    api = EntsoeAPI(config={"api_key": api_key})

    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching ENTSO-E data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)

        if not raw_data:
            logger.error("Error: Failed to fetch data from ENTSO-E API")
            return 1

        logger.debug(f"Raw data keys: {list(raw_data.keys())}")
        log_data = {}
        for k, v in raw_data.items():
            if k == 'xml_responses' and isinstance(v, list):
                log_data[k] = [f"XML Response {i+1} (length: {len(xml)})" for i, xml in enumerate(v)]
            elif isinstance(v, (str, list, dict)) and len(str(v)) > 300:
                 log_data[k] = str(v)[:300] + "..."
            else:
                 log_data[k] = v
        logger.debug(f"Raw data content (summary): {json.dumps(log_data, indent=2)}")

        # Step 2: Parse raw data
        logger.info("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)

        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"Source: {parsed_data.get('source_name', parsed_data.get('source'))}")
        logger.info(f"Area: {area}")
        original_currency = parsed_data.get('currency', Currency.EUR)
        logger.info(f"Currency: {original_currency}")
        source_timezone = parsed_data.get('timezone')
        logger.info(f"API Timezone: {source_timezone}")

        interval_raw_prices = parsed_data.get("interval_raw", {})  # Changed from hourly_raw
        if not interval_raw_prices:
            logger.error("Error: No interval prices found in the parsed data after parsing step.")
            logger.error(f"Available keys: {list(parsed_data.keys())}")
            if 'xml_responses' in raw_data:
                 for i, xml in enumerate(raw_data['xml_responses']):
                     logger.debug(f"--- Raw XML Response {i+1} --- START ---")
                     logger.debug(xml)
                     logger.debug(f"--- Raw XML Response {i+1} --- END ---")
            return 1

        logger.info(f"Found {len(interval_raw_prices)} raw interval prices (before timezone normalization)")
        logger.debug(f"Raw interval prices sample: {dict(list(interval_raw_prices.items())[:5])}")

        # Step 3: Normalize Timezones
        logger.info(f"\nNormalizing timestamps from {source_timezone} to {local_tz_name}...")
        # Use normalize_interval_prices to preserve 15-minute intervals
        normalized_prices = tz_converter.normalize_interval_prices(
            interval_prices=interval_raw_prices,  # Changed from hourly_raw_prices
            source_timezone_str=source_timezone,
            preserve_date=True
        )
        logger.info(f"After normalization: {len(normalized_prices)} price points")
        logger.info(f"Expected: ~192 intervals (15-min for 2 days)")
        logger.debug(f"Normalized prices sample: {dict(list(normalized_prices.items())[:5])}")

        # Step 4: Currency conversion (EUR -> Local currency if needed)
        target_currency = Currency.EUR
        if area.startswith('SE'): target_currency = Currency.SEK
        elif area.startswith('DK'): target_currency = Currency.DKK
        elif area.startswith('NO'): target_currency = Currency.NOK
        elif area == 'GB': target_currency = Currency.GBP

        logger.info(f"\nConverting prices from {original_currency} to {target_currency}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)

        converted_prices = {}
        for hour_key, price_info in normalized_prices.items():
            price_mwh = price_info["price"] if isinstance(price_info, dict) else price_info
            price_converted_mwh = price_mwh
            if original_currency != target_currency:
                price_converted_mwh = await exchange_service.convert(
                    price_mwh,
                    original_currency,
                    target_currency
                )
            price_kwh = price_converted_mwh / 1000
            converted_prices[hour_key] = price_kwh
            if isinstance(normalized_prices[hour_key], dict):
                 normalized_prices[hour_key]['converted_kwh'] = price_kwh
            else:
                 normalized_prices[hour_key] = {'price': price_mwh, 'converted_kwh': price_kwh}

        logger.debug(f"Converted prices sample: {dict(list(converted_prices.items())[:5])}")

        # Step 5: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {original_currency}/MWh")
        logger.info(f"Converted Currency: {target_currency}/kWh")

        today_prices, tomorrow_prices = tz_converter.split_into_today_tomorrow(normalized_prices)

        all_display_prices = {**today_prices, **tomorrow_prices}

        logger.info(f"\nHourly Prices (formatted as HH:00 in target timezone: {local_tz_name}):")
        logger.info(f"{'Hour':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 40)

        for hour_key, price_data in sorted(all_display_prices.items()):
            original_val = price_data['price']
            converted_val = price_data['converted_kwh']
            logger.info(f"{hour_key:<10} {original_val:<15.4f} {converted_val:<15.6f}")

        # Step 6: Validate data completeness
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
            now_utc = datetime.now(timezone.utc)
            now_central_europe = now_utc.astimezone(pytz.timezone('Europe/Brussels'))

            if now_central_europe.hour >= 13 or reference_date_str:
                missing_tomorrow = set(tomorrow_hour_range) - tomorrow_hours_found
                logger.warning(f"Missing tomorrow hours: {', '.join(sorted(missing_tomorrow))}")
            else:
                 logger.info("Tomorrow's data might not be available yet.")

        total_prices = len(today_hours_found) + len(tomorrow_hours_found)
        min_expected = 22
        if reference_date_str:
             min_expected = 24
             if len(tomorrow_hours_found) > 0:
                 min_expected = 46

        if total_prices >= min_expected:
            logger.info("\nTest completed successfully!")
            return 0
        else:
            logger.error(f"\nTest failed: Insufficient price data. Found {total_prices} prices (expected at least {min_expected})")
            return 1

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1

if __name__ == "__main__":
    print("Starting ENTSO-E API full chain test...")
    sys.exit(asyncio.run(main()))

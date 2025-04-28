#!/usr/bin/env python3
"""
Manual full chain test for Nordpool API.

This script performs an end-to-end test of the Nordpool API integration:
1. Fetches real data from the Nordpool API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python nordpool_full_chain.py [area] [date]
    
    area: Optional area code (e.g., SE1, SE2, SE3, SE4, FI, DK1, etc.)
          Defaults to SE3 if not provided
    date: Optional date to fetch data for (format: YYYY-MM-DD)
          Defaults to today if not provided
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import asyncio
import pytz
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Ensure debug logs are shown

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Common Nordpool areas
COMMON_AREAS = [
    'SE1', 'SE2', 'SE3', 'SE4',  # Sweden
    'FI',                        # Finland
    'DK1', 'DK2',                # Denmark
    'NO1', 'NO2', 'NO3', 'NO4', 'NO5',  # Norway
    'EE', 'LV', 'LT',            # Baltic states
    'Oslo', 'Kr.sand', 'Bergen', 'Molde', 'Tr.heim', 'Tromsø',  # Norway cities
    'SYS'                        # System price
]

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Nordpool API integration')
    parser.add_argument('area', nargs='?', default='SE3', 
                        help=f'Area code (e.g., {", ".join(COMMON_AREAS[:5])})')
    parser.add_argument('date', nargs='?', default=None,
                        help='Date to fetch data for (format: YYYY-MM-DD, default: today)')
    args = parser.parse_args()
    
    area = args.area
    reference_date = args.date
    
    # Process reference date if provided
    reference_time = None
    if reference_date:
        try:
            # Parse the date and create a datetime at noon UTC for that date
            reference_time = datetime.strptime(reference_date, '%Y-%m-%d').replace(
                hour=12, minute=0, second=0
            ).astimezone(timezone.utc)
            logger.info(f"Using reference date: {reference_date} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date}. Please use YYYY-MM-DD format.")
            return 1
    
    logger.info(f"\n===== Nordpool API Full Chain Test for {area} =====\n")
    
    # Initialize the API client
    api = NordpoolAPI()
    
    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching Nordpool data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)
        if not raw_data:
            logger.error("Error: Failed to fetch data from Nordpool API")
            return 1
        logger.info(f"Raw data keys: {list(raw_data.keys())}")
        # Print a sample of the raw data (truncated for readability)
        if "raw_data" in raw_data and raw_data["raw_data"]:
            sample_data = str(raw_data["raw_data"])[:300]
            logger.info(f"Raw data sample (truncated): {sample_data}...")
        else:
            logger.warning("No 'raw_data' found in API response")
        
        # Step 2: Use hourly_raw directly (no parse_raw_data)
        logger.info("\nProcessing raw data...")
        hourly_prices = raw_data.get("hourly_raw", {})
        logger.info(f"Source: {raw_data.get('source_name')}")
        logger.info(f"Area: {area}")
        logger.info(f"Currency: {raw_data.get('currency')}")
        logger.info(f"API Timezone: {raw_data.get('timezone')}")
        if not hourly_prices:
            logger.error("Error: No hourly prices found in the raw data")
            return 1
            
        logger.info(f"Found {len(hourly_prices)} hourly prices")
        
        # Step 3: Currency conversion (local currency -> EUR if needed)
        original_currency = raw_data.get('currency', Currency.EUR)
        target_currency = Currency.SEK if area.startswith('SE') else Currency.EUR
        
        logger.info(f"\nConverting prices from {original_currency} to {target_currency}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)
        
        # Convert prices and from MWh to kWh
        converted_prices = {}
        for ts, price in hourly_prices.items():
            # Convert currency if needed
            price_converted = price
            if original_currency != target_currency:
                price_converted = await exchange_service.convert(
                    price, 
                    original_currency,
                    target_currency
                )
            # Convert from MWh to kWh
            price_kwh = price_converted / 1000
            converted_prices[ts] = price_kwh
        
        # Step 4: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {original_currency}/MWh")
        logger.info(f"Converted Currency: {target_currency}/kWh")
        
        # Determine the local timezone based on the area
        local_tz_name = 'Europe/Stockholm'  # Default for Swedish areas
        if area.startswith('FI'):
            local_tz_name = 'Europe/Helsinki'
        elif area.startswith('DK'):
            local_tz_name = 'Europe/Copenhagen'
        elif area.startswith('NO') or area in ['Oslo', 'Kr.sand', 'Bergen', 'Molde', 'Tr.heim', 'Tromsø']:
            local_tz_name = 'Europe/Oslo'
        elif area in ['EE']:
            local_tz_name = 'Europe/Tallinn'
        elif area in ['LV']:
            local_tz_name = 'Europe/Riga'
        elif area in ['LT']:
            local_tz_name = 'Europe/Vilnius'
        
        local_tz = pytz.timezone(local_tz_name)
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            try:
                # Parse the timestamp and convert to local timezone
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(local_tz)
                date_str = dt.strftime('%Y-%m-%d')
                hour_str = dt.strftime('%H:%M')
                
                if date_str not in prices_by_date:
                    prices_by_date[date_str] = {}
                    
                prices_by_date[date_str][hour_str] = {
                    'original': price,
                    'converted': converted_prices.get(ts)
                }
            except ValueError as e:
                logger.warning(f"Could not parse timestamp: {ts}, error: {e}")
        
        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            logger.info(f"\nPrices for {date}:")
            logger.info(f"{'Time':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
            logger.info("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                logger.info(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today = datetime.now(local_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(local_tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # If reference_date is provided, adjust today/tomorrow expectations
        if reference_date:
            ref_date_obj = datetime.strptime(reference_date, '%Y-%m-%d')
            today = ref_date_obj.strftime('%Y-%m-%d')
            tomorrow = (ref_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
            logger.info(f"Using reference dates: today={today}, tomorrow={tomorrow}")
        
        # Check today's data - be more flexible with the requirements
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            logger.info(f"\nFound {len(today_prices)} price points for today ({today})")
            
            if len(today_prices) >= 22:  # Allow for some missing hours
                logger.info(f"✓ Found {len(today_prices)}/24 hourly prices for today")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(today_prices)} hourly prices for today (expected at least 22)")
                
                # If we have coverage information, log it
                if "today_coverage" in raw_data:
                    logger.info(f"Today's coverage: {raw_data['today_coverage']:.1f}%")
                
                # List missing hours for better debugging
                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(today_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    logger.warning(f"Missing hours today: {', '.join(sorted(missing_hours))}")
        else:
            logger.warning(f"\nWarning: No prices found for today ({today})")
        
        # Check tomorrow's data - be more lenient as tomorrow's data may not be available yet
        now_local = datetime.now(local_tz)
        expect_tomorrow_data = now_local.hour >= 13  # Nordpool usually publishes next day prices at ~13:00 CET
        
        # If we specifically requested a date, we should expect tomorrow's data
        if reference_date:
            expect_tomorrow_data = True
            logger.info("Reference date provided - expecting tomorrow's data to be available")
        
        if tomorrow in prices_by_date:
            tomorrow_prices = prices_by_date[tomorrow]
            logger.info(f"\nFound {len(tomorrow_prices)} price points for tomorrow ({tomorrow})")
            
            if len(tomorrow_prices) >= 22:  # Allow for some missing hours
                logger.info(f"✓ Found {len(tomorrow_prices)}/24 hourly prices for tomorrow")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(tomorrow_prices)} hourly prices for tomorrow (expected 24)")
                
                # If we have coverage information, log it
                if "tomorrow_coverage" in raw_data:
                    logger.info(f"Tomorrow's coverage: {raw_data['tomorrow_coverage']:.1f}%")
                
                # List missing hours for better debugging
                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(tomorrow_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    logger.warning(f"Missing hours tomorrow: {', '.join(sorted(missing_hours))}")
        elif expect_tomorrow_data:
            logger.warning(f"\nWarning: No prices found for tomorrow ({tomorrow}) even though it's expected")
        else:
            logger.info(f"\nNote: No prices found for tomorrow ({tomorrow}), but that's expected before 13:00 local time")
        
        # Final validation - check if we have enough data overall to consider the test successful
        total_prices = len(hourly_prices)
        if total_prices >= 22:  # At minimum, we should have most of today's hours
            logger.info("\nTest completed successfully!")
            return 0
        else:
            logger.error(f"\nTest failed: Insufficient price data. Found only {total_prices} prices (expected at least 22)")
            return 1
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    logger.info("Starting Nordpool API full chain test...")
    sys.exit(asyncio.run(main()))
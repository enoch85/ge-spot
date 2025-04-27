#!/usr/bin/env python3
"""
Manual full chain test for ENTSO-E API.

This script performs an end-to-end test of the ENTSO-E API integration:
1. Fetches real data from the ENTSO-E API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python entsoe_full_chain.py [area] [api_key]
    
    area: Optional area code (e.g., SE1, SE2, SE3, SE4, FI, DK1, etc.)
          Defaults to SE3 if not provided
    api_key: Optional ENTSO-E API key
             Can also be provided via ENTSOE_API_KEY environment variable
"""

import sys
import os
import argparse
import getpass
from datetime import datetime, timezone, timedelta
import asyncio
import pytz

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

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
    parser.add_argument('area', nargs='?', default='SE3', 
                        help=f'Area code (e.g., {", ".join(COMMON_AREAS[:5])})')
    parser.add_argument('api_key', nargs='?', default=None,
                        help='ENTSO-E API key (optional if environment variable is set)')
    args = parser.parse_args()
    
    area = args.area
    
    # Get API key from arguments, environment, or prompt
    api_key = args.api_key or os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your ENTSO-E API key: ")
    
    print(f"\n===== ENTSO-E API Full Chain Test for {area} =====\n")
    
    # Initialize the API client with the API key
    api = EntsoeAPI(config={"api_key": api_key})
    
    try:
        # Step 1: Fetch raw data
        print(f"Fetching ENTSO-E data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area)
        
        if not raw_data:
            print("Error: Failed to fetch data from ENTSO-E API")
            return
            
        print(f"Raw data keys: {list(raw_data.keys())}")
        
        # Print a sample of the raw data (truncated for readability)
        raw_data_str = str(raw_data)
        print(f"Raw data sample (truncated): {raw_data_str[:300]}...")
        
        # Step 2: Parse raw data
        print("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)
        
        print(f"Parsed data keys: {list(parsed_data.keys())}")
        print(f"Source: {parsed_data.get('source')}")
        print(f"Area: {parsed_data.get('area')}")
        print(f"Currency: {parsed_data.get('currency')}")
        print(f"API Timezone: {parsed_data.get('api_timezone')}")
        
        # Check if hourly prices are available
        hourly_prices = parsed_data.get("hourly_prices", {})
        if not hourly_prices:
            print("Warning: No hourly prices found in the parsed data")
            return
            
        print(f"Found {len(hourly_prices)} hourly prices")
        
        # Step 3: Currency conversion (EUR -> Local currency)
        target_currency = Currency.SEK if area.startswith('SE') else Currency.EUR
        print(f"\nConverting prices from {parsed_data.get('currency', Currency.EUR)} to {target_currency}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)
        
        # Convert prices from EUR to target currency and from MWh to kWh
        converted_prices = {}
        for ts, price in hourly_prices.items():
            # Convert from EUR to target currency
            price_converted = await exchange_service.convert(
                price, 
                parsed_data.get("currency", Currency.EUR), 
                target_currency
            )
            # Convert from MWh to kWh
            price_kwh = price_converted / 1000
            converted_prices[ts] = price_kwh
        
        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.EUR)}/MWh")
        print(f"Converted Currency: {target_currency}/kWh")
        
        # Determine the local timezone based on the area
        local_tz_name = 'Europe/Stockholm'  # Default for Swedish areas
        if area.startswith('FI'):
            local_tz_name = 'Europe/Helsinki'
        elif area.startswith('DK'):
            local_tz_name = 'Europe/Copenhagen'
        elif area.startswith('NO'):
            local_tz_name = 'Europe/Oslo'
        
        local_tz = pytz.timezone(local_tz_name)
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
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
        
        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            print(f"\nPrices for {date}:")
            original_currency_header = f"{parsed_data.get('currency', Currency.EUR)}/MWh"
            converted_currency_header = f"{target_currency}/kWh"
            print(f"{'Time':<10} {original_currency_header:<15} {converted_currency_header:<15}")
            print("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                print(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today = datetime.now(local_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(local_tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Check today's data
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            print(f"\nFound {len(today_prices)} price points for today ({today})")
            
            if len(today_prices) == 24:
                print("✓ Complete set of 24 hourly prices for today")
            else:
                print(f"⚠ Incomplete data: Found {len(today_prices)} hourly prices for today (expected 24)")
        else:
            print(f"\nWarning: No prices found for today ({today})")
        
        # Check tomorrow's data
        if tomorrow in prices_by_date:
            tomorrow_prices = prices_by_date[tomorrow]
            print(f"\nFound {len(tomorrow_prices)} price points for tomorrow ({tomorrow})")
            
            if len(tomorrow_prices) == 24:
                print("✓ Complete set of 24 hourly prices for tomorrow")
            else:
                print(f"⚠ Incomplete data: Found {len(tomorrow_prices)} hourly prices for tomorrow (expected 24)")
        else:
            print(f"\nWarning: No prices found for tomorrow ({tomorrow})")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting ENTSO-E API full chain test...")
    asyncio.run(main())

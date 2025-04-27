#!/usr/bin/env python3
"""
Manual full chain test for Amber API (Australia).

This script performs an end-to-end test of the Amber API integration:
1. Fetches real data from the Amber API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python amber_full_chain.py [area] [api_key]
    
    area: Optional area code (defaults to NSW)
    api_key: Optional Amber API key
             Can also be provided via AMBER_API_KEY environment variable
"""

import sys
import os
import argparse
import getpass
from datetime import datetime, timezone
import asyncio
import pytz

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.amber import AmberAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Amber API integration')
    parser.add_argument('area', nargs='?', default='NSW',
                        help='Area code (defaults to NSW)')
    parser.add_argument('api_key', nargs='?', default=None,
                        help='Amber API key (optional if environment variable is set)')
    args = parser.parse_args()
    
    area = args.area
    
    # Get API key from arguments, environment, or prompt
    api_key = args.api_key or os.environ.get("AMBER_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your Amber API key: ")
    
    print(f"\n===== Amber API Full Chain Test for {area} =====\n")
    
    # Initialize the API client with the API key
    api = AmberAPI(config={"api_key": api_key})
    
    try:
        # Step 1: Fetch raw data
        print(f"Fetching Amber data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area)
        
        if not raw_data:
            print("Error: Failed to fetch data from Amber API")
            return
            
        # Print a sample of the raw data (truncated for readability)
        if isinstance(raw_data, list):
            print(f"Received {len(raw_data)} data points")
            if raw_data:
                print(f"First data point sample: {raw_data[0]}")
        else:
            print(f"Raw data type: {type(raw_data)}")
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
        
        # Step 3: Currency conversion (AUD -> USD)
        print("\nConverting prices from AUD to USD...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)
        
        # Convert prices from AUD to USD and from MWh to kWh
        converted_prices = {}
        for ts, price in hourly_prices.items():
            # Convert from AUD to USD
            price_usd = await exchange_service.convert(
                price, 
                parsed_data.get("currency", Currency.AUD), 
                Currency.USD
            )
            # Convert from MWh to kWh
            price_usd_kwh = price_usd / 1000
            converted_prices[ts] = price_usd_kwh
        
        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.AUD)}/MWh")
        print(f"Converted Currency: {Currency.USD}/kWh")
        
        # Group prices by date
        au_tz = pytz.timezone(parsed_data.get('api_timezone', 'Australia/Sydney'))
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            # Parse the timestamp and convert to local timezone
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(au_tz)
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
            print(f"{'Time':<10} {'AUD/MWh':<15} {'USD/kWh':<15}")
            print("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                print(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for the current day
        today = datetime.now(au_tz).strftime('%Y-%m-%d')
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            print(f"\nFound {len(today_prices)} price points for today ({today})")
        else:
            print(f"\nWarning: No prices found for today ({today})")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting Amber API full chain test...")
    asyncio.run(main())
